from typing import Union, Dict, Optional
import torch
import torch.nn as nn

from ding.utils import SequenceType, squeeze, MODEL_REGISTRY
from ding.torch_utils import fc_block, ResFCBlock, ResBlock
from ding.model.common import ReparameterizationHead, RegressionHead, DiscreteHead, MultiHead, \
    FCEncoder


class ConvEncoder(nn.Module):
    r"""
    Overview:
        The ``Convolution Encoder`` used in models. Used to encoder raw 2-dim observation.
    Interfaces:
        ``__init__``, ``forward``
    """

    def __init__(
            self,
            obs_shape: SequenceType,
            hidden_size_list: SequenceType = [32, 64, 64, 128],
            activation: Optional[nn.Module] = nn.ReLU(),
            norm_type: Optional[str] = None
    ) -> None:
        r"""
        Overview:
            Init the Convolution Encoder according to arguments.
        Arguments:
            - obs_shape (:obj:`SequenceType`): Sequence of ``in_channel``, some ``output size``
            - hidden_size_list (:obj:`SequenceType`): The collection of ``hidden_size``
            - activation (:obj:`nn.Module`):
                The type of activation to use in the conv ``layers`` and ``ResBlock``,
                if ``None`` then default set to ``nn.ReLU()``
            - norm_type (:obj:`str`):
                The type of normalization to use, see ``ding.torch_utils.ResBlock`` for more details
        """
        super(ConvEncoder, self).__init__()
        self.obs_shape = obs_shape
        self.act = activation
        self.hidden_size_list = hidden_size_list
        self.hidden_size_list = [4, 4, 4]

        layers = []
        kernel_size = [1, 1, 1]
        stride = [1, 1, 1]
        input_size = obs_shape[0]  # in_channel
        for i in range(len(kernel_size)):
            layers.append(nn.Conv2d(input_size, hidden_size_list[i], kernel_size[i], stride[i]))
            layers.append(self.act)
            input_size = hidden_size_list[i]
        assert len(set(hidden_size_list[3:-1])) <= 1, "Please indicate the same hidden size for res block parts"
        for i in range(3, len(self.hidden_size_list) - 1):
            layers.append(ResBlock(self.hidden_size_list[i], activation=self.act, norm_type=norm_type))
        layers.append(nn.Flatten())
        self.main = nn.Sequential(*layers)

        flatten_size = self._get_flatten_size()
        self.mid = nn.Linear(flatten_size, hidden_size_list[-1])

    def _get_flatten_size(self) -> int:
        r"""
        Overview:
            Get the encoding size after ``self.main`` to get the number of ``in-features`` to feed to ``nn.Linear``.
        Arguments:
            - x (:obj:`torch.Tensor`): Encoded Tensor after ``self.main``
        Returns:
            - outputs (:obj:`torch.Tensor`): Size int, also number of in-feature
        """
        test_data = torch.randn(1, *self.obs_shape)
        print("test_data = ", test_data)
        print("test data.shape = ", test_data.shape)
        with torch.no_grad():
            output = self.main(test_data)
        return output.shape[1]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        r"""
        Overview:
            Return embedding tensor of the env observation
        Arguments:
            - x (:obj:`torch.Tensor`): Env raw observation
        Returns:
            - outputs (:obj:`torch.Tensor`): Embedding tensor
        """
        # print("x = ", x)
        # print(x.shape)
        x = x.float()
        x = self.main(x)
        # print("x = ", x)
        x = self.mid(x)
        return x


@MODEL_REGISTRY.register('vac_overcooked')
class VAC(nn.Module):
    r"""
    Overview:
        The VAC model.
    Interfaces:
        ``__init__``, ``forward``, ``compute_actor``, ``compute_critic``
    """
    mode = ['compute_actor', 'compute_critic', 'compute_actor_critic']

    def __init__(
            self,
            obs_shape: Union[int, SequenceType],
            action_shape: Union[int, SequenceType],
            share_encoder: bool = True,
            continuous: bool = False,
            encoder_hidden_size_list: SequenceType = [128, 128, 64],
            actor_head_hidden_size: int = 64,
            actor_head_layer_num: int = 2,
            critic_head_hidden_size: int = 64,
            critic_head_layer_num: int = 1,
            activation: Optional[nn.Module] = nn.ReLU(),
            norm_type: Optional[str] = None,
    ) -> None:
        r"""
        Overview:
            Init the VAC Model according to arguments.
        Arguments:
            - obs_shape (:obj:`Union[int, SequenceType]`): Observation's space.
            - action_shape (:obj:`Union[int, SequenceType]`): Action's space.
            - share_encoder (:obj:`bool`): Whether share encoder.
            - continuous (:obj:`bool`): Whether collect continuously.
            - encoder_hidden_size_list (:obj:`SequenceType`): Collection of ``hidden_size`` to pass to ``Encoder``
            - actor_head_hidden_size (:obj:`Optional[int]`): The ``hidden_size`` to pass to actor-nn's ``Head``.
            - actor_head_layer_num (:obj:`int`):
                The num of layers used in the network to compute Q value output for actor's nn.
            - critic_head_hidden_size (:obj:`Optional[int]`): The ``hidden_size`` to pass to critic-nn's ``Head``.
            - critic_head_layer_num (:obj:`int`):
                The num of layers used in the network to compute Q value output for critic's nn.
            - activation (:obj:`Optional[nn.Module]`):
                The type of activation function to use in ``MLP`` the after ``layer_fn``,
                if ``None`` then default set to ``nn.ReLU()``
            - norm_type (:obj:`Optional[str]`):
                The type of normalization to use, see ``ding.torch_utils.fc_block`` for more details`
        """
        super(VAC, self).__init__()
        obs_shape: int = squeeze(obs_shape)
        action_shape: int = squeeze(action_shape)
        self.obs_shape, self.action_shape = obs_shape, action_shape
        # Encoder Type
        
        if isinstance(obs_shape, int) or len(obs_shape) == 1:
            encoder_cls = FCEncoder
        elif len(obs_shape) == 3:
            encoder_cls = ConvEncoder
        else:
            raise RuntimeError(
                "not support obs_shape for pre-defined encoder: {}, please customize your own DQN".format(obs_shape)
            )
        self.share_encoder = share_encoder
        if self.share_encoder:
            self.encoder = encoder_cls(obs_shape, encoder_hidden_size_list, activation=activation, norm_type=norm_type)
        else:
            self.actor_encoder = encoder_cls(
                obs_shape, encoder_hidden_size_list, activation=activation, norm_type=norm_type
            )
            self.critic_encoder = encoder_cls(
                obs_shape, encoder_hidden_size_list, activation=activation, norm_type=norm_type
            )
        # Head Type
        self.critic_head = RegressionHead(
            critic_head_hidden_size, 1, critic_head_layer_num, activation=activation, norm_type=norm_type
        )
        self.continuous = continuous
        if self.continuous:
            self.multi_head = False
            self.actor_head = ReparameterizationHead(
                actor_head_hidden_size,
                action_shape,
                actor_head_layer_num,
                sigma_type='independent',
                activation=activation,
                norm_type=norm_type
            )
        else:
            actor_head_cls = DiscreteHead
            multi_head = not isinstance(action_shape, int)
            self.multi_head = multi_head
            if multi_head:
                self.actor_head = MultiHead(
                    actor_head_cls,
                    actor_head_hidden_size,
                    action_shape,
                    layer_num=actor_head_layer_num,
                    activation=activation,
                    norm_type=norm_type
                )
            else:
                self.actor_head = actor_head_cls(
                    actor_head_hidden_size,
                    action_shape,
                    actor_head_layer_num,
                    activation=activation,
                    norm_type=norm_type
                )
        # must use list, not nn.ModuleList
        if self.share_encoder:
            self.actor = [self.encoder, self.actor_head]
            self.critic = [self.encoder, self.critic_head]
        else:
            self.actor = [self.actor_encoder, self.actor_head]
            self.critic = [self.critic_encoder, self.critic_head]
        # for convenience of call some apis(such as: self.critic.parameters()), but may cause
        # misunderstanding when print(self)
        self.actor = nn.ModuleList(self.actor)
        self.critic = nn.ModuleList(self.critic)

    def forward(self, inputs: Union[torch.Tensor, Dict], mode: str) -> Dict:
        r"""
        Overview:
            Use encoded embedding tensor to predict output.
            Parameter updates with VAC's MLPs forward setup.
        Arguments:
            Forward with ``'compute_actor'`` or ``'compute_critic'``:
                - inputs (:obj:`torch.Tensor`):
                    The encoded embedding tensor, determined with given ``hidden_size``, i.e. ``(B, N=hidden_size)``.
                    Whether ``actor_head_hidden_size`` or ``critic_head_hidden_size`` depend on ``mode``.
        Returns:
            - outputs (:obj:`Dict`):
                Run with encoder and head.

                Forward with ``'compute_actor'``, Necessary Keys:
                    - logit (:obj:`torch.Tensor`): Logit encoding tensor, with same size as input ``x``.

                Forward with ``'compute_critic'``, Necessary Keys:
                    - value (:obj:`torch.Tensor`): Q value tensor with same size as batch size.
        Shapes:
            - inputs (:obj:`torch.Tensor`): :math:`(B, N)`, where B is batch size and N corresponding ``hidden_size``
            - logit (:obj:`torch.FloatTensor`): :math:`(B, N)`, where B is batch size and N is ``action_shape``
            - value (:obj:`torch.FloatTensor`): :math:`(B, )`, where B is batch size.

        Actor Examples:
            >>> model = VAC(64,128)
            >>> inputs = torch.randn(4, 64)
            >>> actor_outputs = model(inputs,'compute_actor')
            >>> assert actor_outputs['logit'].shape == torch.Size([4, 128])

        Critic Examples:
            >>> model = VAC(64,64)
            >>> inputs = torch.randn(4, 64)
            >>> critic_outputs = model(inputs,'compute_critic')
            >>> critic_outputs['value']
            tensor([0.0252, 0.0235, 0.0201, 0.0072], grad_fn=<SqueezeBackward1>)

        Actor-Critic Examples:
            >>> model = VAC(64,64)
            >>> inputs = torch.randn(4, 64)
            >>> outputs = model(inputs,'compute_actor_critic')
            >>> outputs['value']
            tensor([0.0252, 0.0235, 0.0201, 0.0072], grad_fn=<SqueezeBackward1>)
            >>> assert outputs['logit'].shape == torch.Size([4, 64])

        """
        assert mode in self.mode, "not support forward mode: {}/{}".format(mode, self.mode)
        return getattr(self, mode)(inputs)

    def compute_actor(self, x: torch.Tensor) -> Dict:
        r"""
        Overview:
            Execute parameter updates with ``'compute_actor'`` mode
            Use encoded embedding tensor to predict output.
        Arguments:
            - inputs (:obj:`torch.Tensor`):
                The encoded embedding tensor, determined with given ``hidden_size``, i.e. ``(B, N=hidden_size)``.
                ``hidden_size = actor_head_hidden_size``
        Returns:
            - outputs (:obj:`Dict`):
                Run with encoder and head.

        ReturnsKeys:
            - logit (:obj:`torch.Tensor`): Logit encoding tensor, with same size as input ``x``.
        Shapes:
            - logit (:obj:`torch.FloatTensor`): :math:`(B, N)`, where B is batch size and N is ``action_shape``

        Examples:
            >>> model = VAC(64,64)
            >>> inputs = torch.randn(4, 64)
            >>> actor_outputs = model(inputs,'compute_actor')
            >>> assert actor_outputs['action'].shape == torch.Size([4, 64])
        """
        if self.share_encoder:
            x = self.encoder(x)
        else:
            x = self.actor_encoder(x)
        x = self.actor_head(x)
        if self.continuous:
            x = {'logit': [x['mu'], x['sigma']]}
        return x

    def compute_critic(self, x: torch.Tensor) -> Dict:
        r"""
        Overview:
            Execute parameter updates with ``'compute_critic'`` mode
            Use encoded embedding tensor to predict output.
        Arguments:
            - inputs (:obj:`torch.Tensor`):
                The encoded embedding tensor, determined with given ``hidden_size``, i.e. ``(B, N=hidden_size)``.
                ``hidden_size = critic_head_hidden_size``
        Returns:
            - outputs (:obj:`Dict`):
                Run with encoder and head.

                Necessary Keys:
                    - value (:obj:`torch.Tensor`): Q value tensor with same size as batch size.
        Shapes:
            - value (:obj:`torch.FloatTensor`): :math:`(B, )`, where B is batch size.

        Examples:
            >>> model = VAC(64,64)
            >>> inputs = torch.randn(4, 64)
            >>> critic_outputs = model(inputs,'compute_critic')
            >>> critic_outputs['value']
            tensor([0.0252, 0.0235, 0.0201, 0.0072], grad_fn=<SqueezeBackward1>)
        """
        if self.share_encoder:
            x = self.encoder(x)
        else:
            x = self.critic_encoder(x)
        x = self.critic_head(x)
        return {'value': x['pred']}

    def compute_actor_critic(self, x: torch.Tensor) -> Dict:
        r"""
        Overview:
            Execute parameter updates with ``'compute_actor_critic'`` mode
            Use encoded embedding tensor to predict output.
        Arguments:
            - inputs (:obj:`torch.Tensor`): The encoded embedding tensor.

        Returns:
            - outputs (:obj:`Dict`):
                Run with encoder and head.

        ReturnsKeys:
            - logit (:obj:`torch.Tensor`): Logit encoding tensor, with same size as input ``x``.
            - value (:obj:`torch.Tensor`): Q value tensor with same size as batch size.
        Shapes:
            - logit (:obj:`torch.FloatTensor`): :math:`(B, N)`, where B is batch size and N is ``action_shape``
            - value (:obj:`torch.FloatTensor`): :math:`(B, )`, where B is batch size.

        Examples:
            >>> model = VAC(64,64)
            >>> inputs = torch.randn(4, 64)
            >>> outputs = model(inputs,'compute_actor_critic')
            >>> outputs['value']
            tensor([0.0252, 0.0235, 0.0201, 0.0072], grad_fn=<SqueezeBackward1>)
            >>> assert outputs['logit'].shape == torch.Size([4, 64])


        .. note::
            ``compute_actor_critic`` interface aims to save computation when shares encoder.
            Returning the combination dictionry.

        """
        # print("origin input x shape is:", x.shape)
        if self.share_encoder:
            actor_embedding = critic_embedding = self.encoder(x)
        else:
            actor_embedding = self.actor_encoder(x)
            critic_embedding = self.critic_encoder(x)
        # print("critic_embedding is :", critic_embedding)
        # print("critic_embedding shape is :", critic_embedding.shape)
        value = self.critic_head(critic_embedding)
        actor_output = self.actor_head(actor_embedding)
        if self.continuous:
            logit = [actor_output['mu'], actor_output['sigma']]
        else:
            logit = actor_output['logit']
        return {'logit': logit, 'value': value['pred']}
