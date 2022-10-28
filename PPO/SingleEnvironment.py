from PPO.PPOAlgorithm import PPO
from utils import Logger
import numpy as np
import torch
from mpi4py import MPI as mpi
import time

mpi_comm = mpi.COMM_WORLD
mpi_rank = mpi_comm.Get_rank()

class SwarmMemory():
    def __init__(self, robotsCount = 0):
        self.robotMemory = [Memory() for _ in range(robotsCount)]
        self.currentTerminalStates = [False for _ in range(robotsCount)]

    def __getitem__(self, item):
        return self.robotMemory[item]

    # Gets relative Index according to currentTerminalStates
    def getRelativeIndices(self):
        relativeIndices = []
        for i in range(len(self.currentTerminalStates)):
            if not self.currentTerminalStates[i]:
                relativeIndices.append(i)

        return relativeIndices

    def insertState(self, laser, orientation, distance, velocity):
        relativeIndices = self.getRelativeIndices()
        for i in range(len(relativeIndices)):
            self.robotMemory[relativeIndices[i]].states.append([laser[i], orientation[i], distance[i], velocity[i]])

    def insertAction(self, action):
        relativeIndices = self.getRelativeIndices()
        for i in range(len(relativeIndices)):
            self.robotMemory[relativeIndices[i]].actions.append(action[i])

    def insertReward(self, reward):
        relativeIndices = self.getRelativeIndices()
        for i in range(len(relativeIndices)):
            self.robotMemory[relativeIndices[i]].rewards.append(reward[i])

    def insertLogProb(self, logprob):
        relativeIndices = self.getRelativeIndices()
        for i in range(len(relativeIndices)):
            self.robotMemory[relativeIndices[i]].logprobs.append(logprob[i])

    def insertReachedGoal(self, reachedGoal, isTerminal):
        terminalGoal = np.logical_and(reachedGoal, isTerminal)
        relativeIndices = self.getRelativeIndices()
        for idx in np.where(isTerminal)[0]:
            self.robotMemory[relativeIndices[idx]].reached_goal.append(terminalGoal[idx])

    def insertIsTerminal(self, isTerminal):
        relativeIndices = self.getRelativeIndices()
        for i in range(len(relativeIndices)):
            self.robotMemory[relativeIndices[i]].is_terminals.append(isTerminal[i])
            if isTerminal[i]:
                self.currentTerminalStates[relativeIndices[i]] = True

        # check if currentTerminalStates is all True
        if all(self.currentTerminalStates):
            self.currentTerminalStates = [False for _ in range(len(self.currentTerminalStates))]

    def getStatesOfAllRobots(self):
        laser = []
        orientation = []
        distance = []
        velocity = []
        for robotmemory in self.robotMemory:
            for state in robotmemory.states:
                laser.append(state[0])
                orientation.append(state[1])
                distance.append(state[2])
                velocity.append(state[3])

        return [torch.stack(laser), torch.stack(orientation), torch.stack(distance), torch.stack(velocity)]

    def getActionsOfAllRobots(self):
        actions = []
        for robotmemory in self.robotMemory:
            for action in robotmemory.actions:
                actions.append(action)

        return actions

    def getLogProbsOfAllRobots(self):
        logprobs = []
        for robotmemory in self.robotMemory:
            for logprob in robotmemory.logprobs:
                logprobs.append(logprob)

        return logprobs

    def clear_memory(self):
        for memory in self.robotMemory:
            memory.clear_memory()

    def __add__(self, other):
        new_memory = SwarmMemory()
        new_memory.robotMemory += self.robotMemory
        new_memory.currentTerminalStates += self.currentTerminalStates
        if other is not None:
            new_memory.robotMemory += other.robotMemory
            new_memory.currentTerminalStates += other.currentTerminalStates
        return new_memory

    def __iadd__(self, other):
        if other is not None:
            self.robotMemory += other.robotMemory
            self.currentTerminalStates += other.currentTerminalStates
        return self

    def __len__(self):
        length = 0
        for memory in self.robotMemory:
            length += len(memory)
        return length


class Memory:   # collected from old policy
    def __init__(self):
        self.states = []
        self.actions = []
        self.rewards = []
        self.is_terminals = []
        self.reached_goal = []
        self.logprobs = []

    def clear_memory(self):
        del self.states[:]
        del self.actions[:]
        del self.rewards[:]
        del self.is_terminals[:]
        del self.reached_goal[:]
        del self.logprobs[:]

    def __len__(self):
        return len(self.states)

def train(env_name, env, solved_percentage, input_style,
          max_episodes, max_timesteps, update_experience, action_std, K_epochs, eps_clip,
          gamma, lr, betas, ckpt_folder, restore, tensorboard, sync_experience, scan_size=121, log_interval=10, batch_size=1):

    # Tensorboard
    logger = None
    if mpi_rank == 0:
        logger = Logger(log_dir=ckpt_folder, update_interval=log_interval)
        logger.set_logging(tensorboard)

    memory = SwarmMemory(env.getNumberOfRobots())
    memorybundle = SwarmMemory()

    ppo = PPO(scan_size, action_std, input_style, lr, betas, gamma, K_epochs, eps_clip, logger=logger)
    env.setUISaveListener(ppo, ckpt_folder, env_name)

    ckpt = ckpt_folder+'/PPO_continuous_'+env_name+'.pth'
    if restore:
        if mpi_rank == 0:
            print('Load checkpoint from {}'.format(ckpt), flush=True)
            pretrained_model = torch.load(ckpt, map_location=lambda storage, loc: storage)
        pretrained_model = mpi_comm.bcast(pretrained_model)
        ppo.policy.load_state_dict(pretrained_model)

    #logger.build_graph(ppo.policy.actor, ppo.policy.device)
    #logger.build_graph(ppo.policy.critic, ppo.policy.device)

    running_reward, avg_length = 0, 0
    best_reward = 0
    # training loop
    starttime = time.time()
    for i_episode in range(1, max_episodes+1):
        states = env.reset()
        robot_count = mpi_comm.reduce(env.getNumberOfRobots())
        if mpi_rank == 0:
            logger.set_episode(i_episode)
            logger.set_number_of_agents(robot_count)

        env_not_done = True
        for t in range(max_timesteps):

            if env_not_done:
                # Run old policy
                actions = ppo.select_action(states, memory)

                states, rewards, dones, reachedGoals = env.step(actions)

                running_reward += np.mean(rewards)

                memory.insertReward(rewards)
                #memory.insertReachedGoal(reachedGoals, dones) not used just now
                memory.insertIsTerminal(dones)
            else:
                states, rewards, dones, reachedGoals = [], [], [], []

            reachedGoals = mpi_comm.reduce(reachedGoals)
            if mpi_rank == 0:
                logger.log_objective(reachedGoals)

            experience = mpi_comm.allreduce(len(memory))
            if experience >= sync_experience:
                memorybundle += mpi_comm.reduce(memory)
                memory.clear_memory()
                experience = mpi_comm.bcast(len(memorybundle))
                if experience >= update_experience:
                    if mpi_rank == 0:
                        print('Train Network at Episode {} with {} Experiences'.format(i_episode, len(memorybundle)), flush=True)
                        print('Time: {}'.format(time.time() - starttime), flush=True)
                        starttime = time.time()
                        ppo.update(memorybundle, batch_size)
                        print("done training", flush=True)
                        memorybundle.clear_memory()
                    pth = mpi_comm.bcast(ppo.policy.state_dict())
                    if mpi_rank != 0:
                        ppo.policy.load_state_dict(pth)
                    print("done", flush=True)

            if env_not_done and env.is_done():
                env_not_done = False
                avg_length += t

        done = False
        if mpi_rank == 0 and logger.percentage_objective_reached() >= solved_percentage:
            print(f"Percentage of: {logger.percentage_objective_reached():.2f} reached!", flush=True)
            torch.save(ppo.policy.state_dict(), ckpt_folder + '/PPO_continuous_{}_solved.pth'.format(env_name))
            print('Save as solved!', flush=True)
            done = True
        done = mpi_comm.bcast(done)
        if done:
            break

        if i_episode % log_interval == 0:
            avg_length = mpi_comm.reduce(avg_length)
            running_reward = mpi_comm.reduce(running_reward)
            if mpi_rank == 0:
                avg_length = int(avg_length / log_interval)
                running_reward = (running_reward / log_interval)

                if running_reward > best_reward:
                    best_reward = running_reward
                    torch.save(ppo.policy.state_dict(), ckpt_folder + '/PPO_continuous_{}_best.pth'.format(env_name))
                    print(f'Best performance with avg reward of {best_reward:.2f} saved at episode {i_episode}.', flush=True)
                    print(f'Percentage of objective reached: {logger.percentage_objective_reached():.4f}', flush=True)

                logger.scalar_summary('reward', running_reward)
                logger.scalar_summary('Avg Steps', avg_length)
                logger.summary_objective()
                #logger.summary_actor_output()
                logger.summary_loss()

                if not tensorboard:
                    print(f'Episode: {i_episode}, Avg reward: {running_reward:.2f}, Avg steps: {avg_length:.2f}')

            running_reward, avg_length = 0, 0

    if mpi_rank == 0 and tensorboard:
        logger.close()


def test(env_name, env, render, action_std, input_style, K_epochs, eps_clip, gamma, lr, betas, ckpt_folder, test_episodes, scan_size=121):

    ckpt = ckpt_folder+'/PPO_continuous_'+env_name+'.pth'
    print('Load checkpoint from {}'.format(ckpt))

    memory = SwarmMemory(env.getNumberOfRobots())

    ppo = PPO(scan_size, action_std, input_style, lr, betas, gamma, K_epochs, eps_clip, restore=True, ckpt=ckpt, logger=None)

    episode_reward, time_step = 0, 0
    avg_episode_reward, avg_length = 0, 0

    # test
    for i_episode in range(1, test_episodes+1):
        states = env.reset()
        while True:
            time_step += 1

            # Run old policy
            actions = ppo.select_action_certain(states, memory)

            states, rewards, dones, _ = env.step(actions)
            memory.insertIsTerminal(dones)

            episode_reward += np.sum(rewards)

            if render:
                env.render()

            if env.is_done():
                print('Episode {} \t Length: {} \t Reward: {}'.format(i_episode, time_step, episode_reward))
                avg_episode_reward += episode_reward
                avg_length += time_step
                memory.clear_memory()
                time_step, episode_reward = 0, 0
                break

    print('Test {} episodes DONE!'.format(test_episodes))
    print('Avg episode reward: {} | Avg length: {}'.format(avg_episode_reward/test_episodes, avg_length/test_episodes))