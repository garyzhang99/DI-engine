from time import time
from numpy.core.shape_base import stack
import pytest
import numpy as np
from dizoo.overcooked.envs import OvercookEnv, OvercookGameEnv


@pytest.mark.unittest
class TestOvercooked:

    def test_overcook(self):
        concat_obs = True
        num_agent = 2
        sum_rew = 0.0
        env = OvercookEnv({'concat_obs': concat_obs})
        # print(env.info())
        obs = env.reset()
        for k, v in obs.items():
            # print("obs space is", env.info().obs_space.shape)
            if concat_obs:
                assert v.shape == env.info().obs_space.shape[k]
            else:
                assert len(v) == len(env.info().obs_space.shape[k])
        for _ in range(env._horizon):
            action = np.random.randint(0, 6, (num_agent, ))
            # print("action is:", action)
            timestep = env.step(action)
            obs = timestep.obs
            # print("reward = ", timestep.reward)
            # print("done = ", timestep.done)
            # print("timestep = ", timestep)
            for k, v in obs.items():
                if concat_obs:
                    assert v.shape == env.info().obs_space.shape[k]
                else:
                    assert len(v) == len(env.info().obs_space.shape[k])
            # assert isinstance(timestep, tuple), timestep
        # print("Test done for {} steps".for
        assert timestep.done
        # print("final reward=", timestep.info['final_eval_reward'])
        sum_rew += timestep.info['final_eval_reward'][0]
        print("sum reward is:", sum_rew)
    
    def test_overcook_game(self):
        concat_obs = False
        num_agent = 2
        env = OvercookGameEnv({'concat_obs': concat_obs})
        # print(env.info())
        obs = env.reset()
        # print("obs shape is :", obs.shape)
        for _ in range(env._horizon):
            action = [np.random.randint(0, 6), np.random.randint(0, 6)]
            # print("action is:", action)
            timestep = env.step(action)
            obs = timestep.obs
            print("shaped reward is:", timestep.info[0]['shaped_r_by_agent'], timestep.info[1]['shaped_r_by_agent'])
        assert timestep.done
        print("agent 0 sum reward is:", timestep.info[0]['final_eval_reward'])
        print("agent 1 sum reward is:", timestep.info[1]['final_eval_reward'])

