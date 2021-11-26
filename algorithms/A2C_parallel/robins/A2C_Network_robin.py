from os import name
import logging  
import tensorflow as tf
from tensorflow import keras
from algorithms.A2C_parallel.robins.abstract_model import AbstractModel
import algorithms.A2C_parallel.robins.abstract_model
from tensorflow.keras.layers import Input, Conv1D, Dense, Flatten, Concatenate
from tensorflow.keras.models import Model as KerasModel

from algorithms.A2C_parallel.robins.continous_layer import ContinuousLayer

import numpy as np
from typing import Tuple


class Robin_Network(AbstractModel):
    NEEDED_OBSERVATIONS = ['lidar_0', 'orientation_to_goal', 'distance_to_goal', 'velocity']

    def __init__(self, act_dim, env_dim, args):
        config = {
            'lidar_size': args.number_of_rays,
            'orientation_size': 2,
            'distance_size': 1,
            'velocity_size': 2,
            'stack_size': env_dim[0],
            'clipping_range': 0.2,
            'coefficient_value': 0.5
        }
        super().__init__(config)

        self.config = (config)
        print('Versionen (tf, Keras): ', tf.__version__, keras.__version__)

    @property
    def config(self):
        return self._config

    # @TODO Fix for new env/config
    @config.setter
    def config(self, config):#config_tuple: Tuple[dict, dict]):
        #config, agent_config = config_tuple
       
        # agent_obs = agent_config.getObservationActive()
        # Check whether the agent has the reuired observations
        # if not all(x in agent_obs for x in Robin_Network.NEEDED_OBSERVATIONS):
        #     raise ValueError(f'The Agents observation needs at least these keys: {Robin_Network.NEEDED_OBSERVATIONS}')
        
        # Get stack_size from the agent config an ensure the stack_size of every observation is the same
        # to do Fix Stacksize check
        # stack_size = agent_config['laser_0'][1]
        # assert all([x[1] == stack_size for x in agent_config.values()])
        # config['stack_size'] = stack_size

        # Extract the observation sizes from the agent config
        # config['lidar_size'] = #agent_obs['lidar_0'][0][0]
        # config['orientation_size'] = #agent_obs['orientation_to_goal'][0][0]
        # config['distance_size'] = #agent_obs['distance_to_goal'][0][0]
        # config['velocity_size'] = #agent_obs['velocity'][0][0]
        
        self._config = config

    def build(self):
        input_lidar = self._create_input_layer(self._config['lidar_size'], 'lidar')
        input_orientation = self._create_input_layer(self._config['orientation_size'], 'orientation')
        input_distance = self._create_input_layer(self._config['distance_size'], 'distance')
        input_velocity = self._create_input_layer(self._config['velocity_size'], 'velocity')

        tag = 'body'

        # Lidar Convolutions
        lidar_conv = Conv1D(filters=16, kernel_size=7, strides=3, padding='same', activation='relu', name=tag + '_lidar-conv_1')(input_lidar) # k_s 7 (15) str 3 (7)

        lidar_conv = Conv1D(filters=32, kernel_size=5, strides=2, padding='same', activation='relu', name=tag + '_lidar-conv_2')(lidar_conv)
        lidar_flat = Flatten()(lidar_conv)
        lidar_flat = Dense(units=160, activation='relu', name=tag + '_lidar-dense')(lidar_flat)


        # Orientation 
        orientation_flat = Flatten(name=tag + 'orientation_flat')(input_orientation)

        # Distance
        distance_flat = Flatten(name=tag + '_distance_flat')(input_distance)

        # Velocity 
        velocity_flat = Flatten(name=tag + '_velocity_flat')(input_velocity)

        # Concat layes ¬Lidar
        concated_some = Concatenate()([orientation_flat, distance_flat, velocity_flat])
        concated_some = Dense(units=96, activation='relu')(concated_some)


        # Concat the layers
        concated = Concatenate(name=tag + '_concat')([lidar_flat, concated_some])

        # Dense all
        densed = Dense(units=256, activation='relu', name=tag+'_dense', )(concated)

        # Policy
        mu = Dense(units=2, activation='tanh', name='output_mu')(densed)
        var = ContinuousLayer(name='output_continous')(mu)

        # Value
        value = Dense(units=128, activation='relu', name='out_value_dense')(densed)
        value = Dense(units=1, activation=None, use_bias=False, name='out_value')(value)
        
        # Create the Keras Model
        self._model = KerasModel(inputs=[input_lidar, input_orientation, input_distance, input_velocity], outputs=[mu, var, value])

        # Create the Optimizer
        self._optimizer = keras.optimizers.Adam(learning_rate=0.0001, epsilon=1e-5, clipnorm=1.0)

    def _create_input_layer(self, input_dim, name) -> Input:
        return Input(shape=(input_dim, self._config['stack_size']), dtype='float32', name='input_' + name)

    def _select_action_continuous_clip(self, mu, var):
        return tf.clip_by_value(mu + tf.exp(var) * tf.random.normal(tf.shape(mu)), -1.0, 1.0)
        #return clip(mu + exp(var) * random_normal(shape(mu)), -1.0, 1.0)

    def _neglog_continuous(self, action, mu, var):
        # Cast gedöns notwendig?
        return 0.5 * tf.reduce_sum(tf.square((action - mu) / tf.exp(var)), axis=-1) \
                + 0.5 * tf.math.log(2.0 * np.pi) * tf.cast(tf.shape(action)[-1], dtype='float32') \
                + tf.reduce_sum(var, axis=-1)


    def predict(self, obs_laser, obs_orientation_to_goal, obs_distance_to_goal, obs_velocity):
        '''
        observation: python dict with the keys:
        'laser_0', 'orientation_to_goal', 'distance_to_goal', 'velocity'. 
        shape of each key: (num_agents, size_of_the_obs, stack_size).
        For the lidar with stack_size 4 and 2 agents: (2, 1081, 4)
        '''
        logging.info(f'Tracing predict function of {self.__class__}')
        net_out = self._model([obs_laser, obs_orientation_to_goal, obs_distance_to_goal, obs_velocity])
        
        selected_action, neglog = self._postprocess_predictions(*net_out)

        return [selected_action, net_out[2], neglog]

    def _postprocess_predictions(self, mu, var, val):
        """
        Calculates the action selection and the neglog based on the network output mu, var, value.

        Parameters:
            mu (Tensor (None, 2)): The mu output from the dnn.
            var (Tensor (None, 2)): The var output from the dnn.
            val (Tensor (None, 1)): The value output from the dnn.

        Returns:
            selected_action (Tensor (None, 2))
            neglog (Tensor (None,))

        """
        selected_action = self._select_action_continuous_clip(mu, var)
        neglog = self._neglog_continuous(selected_action, mu, var)
        return (selected_action, neglog)        


    # def train(self, observation, action):
    #     with tf.GradientTape() as tape:
    #         #print(observation["laser_0"].shape)
    #         net_out = self._model(([observation["laser_0"], observation["orientation_to_goal"],
    #                                observation["distance_to_goal"], observation["velocity"]]))
    #         loss = self.calculate_loss(observation, action, net_out)
    #
    #     gradients = tape.gradient(loss, self._model.trainable_variables)
    #     self._optimizer.apply_gradients(zip(gradients, self._model.trainable_variables))
    #
    #     return {'loss': loss}

    def train(self, observation, action):
        logging.info(f'Tracing train function of {self.__class__}')
        with tf.GradientTape() as tape:
            net_out = self._model(observation.values())
            loss = self.calculate_loss(observation, action, net_out)

        gradients = tape.gradient(loss, self._model.trainable_variables)
        self._optimizer.apply_gradients(zip(gradients, self._model.trainable_variables))

        return {'loss': loss}

    def calculate_loss(self, observation, action, net_out):
        neglogp = self._neglog_continuous(action['action'], net_out[0], net_out[1])
            
        ratio = tf.exp(action['neglog_policy'] - neglogp)
        pg_loss = -action['advantage'] * ratio
        pg_loss_cliped = -action['advantage'] * tf.clip_by_value(ratio, 1.0 - self._config['clipping_range'], 1.0 + self._config['clipping_range'])

        pg_loss = tf.reduce_mean(tf.maximum(pg_loss, pg_loss_cliped))
        #print(tf.squeeze(net_out[2]), net_out[2], action['reward'],  self._config['coefficient_value'])
        value_loss = keras.losses.mean_squared_error(net_out[2], tf.convert_to_tensor(action['reward'], dtype='float32')) * self._config['coefficient_value']
        
        loss = pg_loss + value_loss

        return loss


    def load_weights(self, path):
        self._model.load_weights(path)

    def load_model(self, path):
        # path = path.replace('\\', '/')
        print(path)
        self._model = tf.keras.models.load_model(path)
        self.print_summary()

    def pedict_certain(self, s):
        """
        Use the actor to predict the next action to take, using the policy
        :param s: state of a single robot
        :return: [actions]
        """

        laser = np.array([np.array(s[i][0]) for i in range(0, len(s))]).swapaxes(0, 1)
        orientation = np.array([np.array(s[i][1]) for i in range(0, len(s))]).swapaxes(0, 1)
        distance = np.array([np.array(s[i][2]) for i in range(0, len(s))]).swapaxes(0, 1)
        velocity = np.array([np.array(s[i][3]) for i in range(0, len(s))]).swapaxes(0, 1)

        net_out = self._model([np.expand_dims(laser, 0), np.expand_dims(orientation, 0), np.expand_dims(distance, 0), np.expand_dims(velocity, 0)])

       # selected_action, criticValue, neglog = self.predict(np.expand_dims(laser, 0), np.expand_dims(orientation, 0),
       #                                                     np.expand_dims(distance, 0), np.expand_dims(velocity, 0))

        return (net_out[0], None)


    def print_summary(self):
        self._model.summary()

    def set_model_weights(self, weights):
        self._model.set_weights(weights)

    def get_model_weights(self):
        return self._model.get_weights()

    def save_model_weights(self, path):
        self._model.save_weights(path + '.h5')



