import logging
import tensorflow as tf
from tensorflow import keras
from algorithms.PPO_parallel.abstract_model import AbstractModel
from tensorflow.keras.layers import Input, Conv1D, Flatten, Concatenate, Lambda, Dense, Conv2D, MaxPooling2D
from tensorflow.keras.models import Model as KerasModel
from algorithms.PPO_parallel.continous_layer import ContinuousLayer
import numpy as np
from DebugListener import DebugListener

physical_devices = tf.config.experimental.list_physical_devices('GPU')
if len(physical_devices) > 0:
    tf.config.experimental.set_memory_growth(physical_devices[0], True)

class PPO_Network(AbstractModel):
    NEEDED_OBSERVATIONS = ['lidar_0', 'orientation_to_goal', 'distance_to_goal', 'velocity']

    def __init__(self, act_dim, env_dim, args, load_weights=False):
        config = {
            'lidar_size': args.number_of_rays,
            'orientation_size': 2,
            'distance_size': 1,
            'velocity_size': 2,
            'stack_size': env_dim[0],
            'clipping_range': 0.1, #0.2
            'coefficient_value': 0.8 #0.5
        }
        self.args = args
        super().__init__(config)

        self.debugListener = DebugListener()

        self.config = (config)
        self._load_weights = load_weights
        print('Versionen (tf, Keras): ', tf.__version__, keras.__version__)

    @property
    def config(self):
        return self._config

    @config.setter
    def config(self, config):
        self._config = config

    def build(self):
        #input_lidar = self._create_input_layer(self._config['lidar_size'], 'lidar')
        input_lidar = Input(shape=(121, 121, self._config['stack_size']), dtype='float32', name='input_lidar')
        input_orientation = self._create_input_layer(self._config['orientation_size'], 'orientation')
        input_distance = self._create_input_layer(self._config['distance_size'], 'distance')
        input_velocity = self._create_input_layer(self._config['velocity_size'], 'velocity')

        tag = 'body'

        if not self._load_weights:
            lidar_conv = Conv2D(16, (16, 16), strides=(8, 8), activation='relu')(input_lidar)
            lidar_conv = Conv2D(32, (8, 8), strides=(4, 4), activation='relu')(lidar_conv)
            #lidar_conv = Conv2D(16, (16, 16), strides=(4, 4), activation='relu')(input_lidar)
            #lidar_conv = Conv2D(32, (8, 8), strides=(2, 2), activation='relu')(lidar_conv)
            #lidar_conv = Conv2D(128, (3, 3), activation='relu')(lidar_conv)
        else:
            m = PPO_Network(None, [4], self.args, False)
            m.build()
            path = "models/weights.h5"
            m.load_weights(path)

            layer_names = ["conv2d", "conv2d_1", "conv2d_2"]
            layers = [m._model.get_layer(layer_name) for layer_name in layer_names]

            lidar_conv = layers[0](input_lidar)
            lidar_pool = MaxPooling2D(pool_size=(2, 2), strides=(2, 2), padding='valid')(lidar_conv)
            lidar_conv = layers[1](lidar_pool)
            lidar_pool = MaxPooling2D(pool_size=(2, 2), strides=(2, 2), padding='valid')(lidar_conv)
            lidar_conv = layers[2](lidar_pool)

        # Lidar Convolutions
        #lidar_conv = Conv1D(filters=16, kernel_size=7, strides=3, padding='same', activation='relu', name=tag + '_lidar-conv_1')(input_lidar) # k_s 7 (15) str 3 (7)
        #lidar_conv = Conv1D(filters=32, kernel_size=5, strides=2, padding='same', activation='relu', name=tag + '_lidar-conv_1')(input_lidar) # k_s 7 (15) str 3 (7)

        #lidar_conv = Conv1D(filters=32, kernel_size=5, strides=2, padding='same', activation='relu', name=tag + '_lidar-conv_2')(lidar_conv)
        #lidar_conv = Conv1D(filters=32, kernel_size=3, strides=2, padding='same', activation='relu', name=tag + '_lidar-conv_2')(lidar_conv)

        lidar_flat = Flatten()(lidar_conv)
        #lidar_flat = Dense(units=160, activation='relu', name=tag + '_lidar-dense')(lidar_flat)
        lidar_flat = Dense(units=128, activation='relu', name=tag + '_lidar-dense')(lidar_flat)

        # Orientation 
        orientation_flat = Flatten(name=tag + 'orientation_flat')(input_orientation)

        # Distance
        distance_flat = Flatten(name=tag + '_distance_flat')(input_distance)

        # Velocity 
        velocity_flat = Flatten(name=tag + '_velocity_flat')(input_velocity)

        # Concat layes ¬Lidar
        #concated_some = Concatenate()([orientation_flat, distance_flat, velocity_flat])
        #concated_some = Dense(units=96, activation='relu')(concated_some)
        concated_some = Concatenate()([orientation_flat, distance_flat, velocity_flat, lidar_flat])
        densed = Dense(units=128, activation='relu')(concated_some)
        densed = Dense(units=128, activation='relu')(densed)

        # Concat the layers
        # concated = Concatenate(name=tag + '_concat')([lidar_flat, concated_some])

        # Dense all
        #densed = Dense(units=256, activation='relu', name=tag+'_dense', )(concated)
        #densed = Dense(units=9, activation='relu', name=tag+'_dense', )(concated)


        # Policy
        mu = Dense(units=2, activation='tanh', name='output_mu')(densed)
        var = Dense(units=2, activation='softplus', name="actor_output_sigma")(densed)
        #var = ContinuousLayer(name='output_continous')(mu) # Lambda(lambda x: x/5)
        #var = ContinuousLayer(name='output_continous')(densed) # Lambda(lambda x: x/5)

        # Value
        value1 = Dense(units=128, activation='relu', name='out_value1_dense')(densed)
        value2 = Dense(units=128, activation='relu', name='out_value2_dense')(densed)
        concat_value = Concatenate()([value1, value2])
        value = Dense(units=1, activation='relu', name='out_value_dense')(concat_value)
        #value = Dense(units=1, activation=None, use_bias=False, name='out_value')(value)
        
        # Create the Keras Model
        self._model = KerasModel(inputs=[input_lidar, input_orientation, input_distance, input_velocity], outputs=[mu, var, value])

        # Create the Optimizer
        self._optimizer = keras.optimizers.Adam(learning_rate=self.args.learningrate, epsilon=1e-5, clipnorm=1.0)

    def _create_input_layer(self, input_dim, name) -> Input:
        return Input(shape=(input_dim, self._config['stack_size']), dtype='float32', name='input_' + name)

    def _select_action_continuous_clip(self, mu, sigma):
        self.debugListener.debug2(sigma)
        return tf.clip_by_value(tf.random.normal(tf.shape(mu), mu, sigma), -1.0, 1.0)

    def _select_action_continuous_clip2(self, mu, var):
        # original, if you restore this. set variance_start in continous layer to 0.0
        #var = tf.Variable([-6, -6], dtype='float32') # why variance so biggg???
        self.debugListener.debug2(var)
        #return tf.clip_by_value(mu + tf.exp(var) * tf.random.normal(tf.shape(mu), 0, 0.5), -1.0, 1.0)
        return tf.clip_by_value(tf.random.normal(tf.shape(mu), mu, tf.sqrt(var)), -1.0, 1.0)
        #return clip(mu + exp(var) * random_normal(shape(mu)), -1.0, 1.0)

    def _neglog_continuous(self, action, mu, sigma):

        variance = tf.math.square(sigma)
        pdf = 1. / tf.math.sqrt(2. * np.pi * variance) * tf.exp(
            -tf.math.square(action - mu) / (2. * variance))
        pdf = tf.reduce_sum(pdf)
        log_pdf = tf.math.log(pdf + tf.keras.backend.epsilon())
        return log_pdf

    def _neglog_continuous2(self, action, mu, var):
        return 0.5 * tf.reduce_sum(tf.square((action - mu) / tf.exp(var)), axis=-1) \
                + 0.5 * tf.math.log(2.0 * np.pi) * tf.cast(tf.shape(action)[-1], dtype='float32') \
                + tf.reduce_sum(var, axis=-1)

    def entropy_continuous(self, sigma):
        #loss_entropy = self.ENTROPY_LOSS_RATIO * K.backend.mean(
        #    -(K.backend.log(2 * np.pi * variance) + 1) / 2)  # see move37 chap 9.5
        loss_entropy = 0.0001 * tf.math.reduce_mean(- (tf.math.log(2 * np.pi * tf.math.square(sigma)) + 1) / 2)
        #return tf.reduce_sum(tf.math.square(sigma) + 0.5 * tf.math.log(2.0 * np.pi * np.e), axis=-1)
        return loss_entropy

    def entropy_continuous2(self, var):
        return tf.reduce_sum(var + 0.5 * tf.math.log(2.0 * np.pi * np.e), axis=-1)

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
        return selected_action, neglog

    def train(self, observation, action):
        logging.info(f'Tracing train function of {self.__class__}')
        with tf.GradientTape() as tape:
            net_out = self._model(observation.values())
            #net_out = self._model(observation['lidar_0'], observation['orientation_to_goal'], observation['distance_to_goal'], observation['velocity'])
            loss = self.calculate_loss(observation, action, net_out)

        self.debugListener.debug(loss)
        gradients = tape.gradient(loss, self._model.trainable_variables)
        self._optimizer.apply_gradients(zip(gradients, self._model.trainable_variables))

        return {'loss': loss}

    def calculate_loss(self, observation, action, net_out):
        neglogp = self._neglog_continuous(action['action'], net_out[0], net_out[1])
            
        ratio = tf.exp(action['neglog_policy'] - neglogp)

        pg_loss = -action['advantage'] * ratio
        pg_loss_cliped = -action['advantage'] * tf.clip_by_value(ratio, 1.0 - self._config['clipping_range'], 1.0 + self._config['clipping_range'])

        pg_loss = tf.reduce_mean(tf.maximum(pg_loss, pg_loss_cliped))

        #pg_loss = action['advantage'] * ratio
        #pg_loss_cliped = action['advantage'] * tf.clip_by_value(ratio, 1.0 - self._config['clipping_range'], 1.0 + self._config['clipping_range'])
        #pg_loss = tf.reduce_mean(tf.minimum(pg_loss, pg_loss_cliped))

        value_loss = keras.losses.mean_squared_error(net_out[2], tf.convert_to_tensor(action['reward'], dtype='float32')) * self._config['coefficient_value']
        
        loss = pg_loss + value_loss - self.entropy_continuous(net_out[1])

        return loss

    def calculate_loss(self, observation, action, net_out):
        neglogp = self._neglog_continuous(action['action'], net_out[0], net_out[1])

        ratio = tf.exp(neglogp - action['neglog_policy'])

        # surrogate1 = ratio * advantage
        # clip_ratio = K.backend.clip(ratio, min_value=1 - self.CLIPPING_LOSS_RATIO,
        #                             max_value=1 + self.CLIPPING_LOSS_RATIO)
        # surrogate2 = clip_ratio * advantage
        # # loss is the mean of the minimum of either of the surrogates
        # loss_actor = - K.backend.mean(K.backend.minimum(surrogate1, surrogate2))
        # # entropy bonus in accordance with move37 explanation https://youtu.be/kWHSH2HgbNQ
        # sigma = y_pred[:, self.action_n:]
        # variance = K.backend.square(sigma)
        # loss_entropy = self.ENTROPY_LOSS_RATIO * K.backend.mean(
        #     -(K.backend.log(2 * np.pi * variance) + 1) / 2)  # see move37 chap 9.5
        # # total bonus is all losses combined. Add MSE-value-loss here as well?
        # return loss_actor + loss_entropy

        pg_loss = action['advantage'] * ratio
        pg_loss_cliped = action['advantage'] * tf.clip_by_value(ratio, 1.0 - self._config['clipping_range'],
                                                                 1.0 + self._config['clipping_range'])

        pg_loss = tf.reduce_mean(tf.minimum(pg_loss, pg_loss_cliped))

        value_loss = keras.losses.mean_squared_error(net_out[2],
                                                     tf.convert_to_tensor(action['reward'], dtype='float32')) * \
                                                     self._config['coefficient_value']

        loss = pg_loss + value_loss - self.entropy_continuous(net_out[1])

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
        #laser = np.array([np.array(s[i][0]) for i in range(0, len(s))]).swapaxes(0, 1)
        laser = np.array([np.array(s[i][0]) for i in range(0, len(s))]).swapaxes(0,2)
        #print("laser_state2: ", laser.shape)
        orientation = np.array([np.array(s[i][1]) for i in range(0, len(s))]).swapaxes(0, 1)
        distance = np.array([np.array(s[i][2]) for i in range(0, len(s))]).swapaxes(0, 1)
        velocity = np.array([np.array(s[i][3]) for i in range(0, len(s))]).swapaxes(0, 1)

        if self.args.lidar_activation:
            return self.make_gradcam_heatmap(laser, orientation, distance, velocity, 1)
        else:
            net_out = self._model([np.expand_dims(laser, 0), np.expand_dims(orientation, 0), np.expand_dims(distance, 0),
                                   np.expand_dims(velocity, 0)])

            return net_out[0], None

    def print_summary(self):
        self._model.summary()

    def set_model_weights(self, weights):
        self._model.set_weights(weights)

    def get_model_weights(self):
        return self._model.get_weights()

    def save_model_weights(self, path):
        self._model.save_weights(path + '.h5')

    def make_gradcam_heatmap(self, laser, orientation, distance, velocity, pred_index=0):
        """

        :param laser:
        :param orientation:
        :param distance:
        :param velocity:
        :param pred_index: 0 for activations of linVel 1 for activations of angular velocity
        :return:
        """

        # First, we create a model that maps the input image to the activations
        # of the last conv layer as well as the output predictions
        grad_model = tf.keras.models.Model(
            [self._model.inputs], [self._model.get_layer('body_lidar-conv_2').output, self._model.output[0]])

        # Then, we compute the gradient of the top predicted class for our input image
        # with respect to the activations of the last conv layer
        with tf.GradientTape() as tape:
            last_conv_layer_output, preds = grad_model([np.expand_dims(laser, 0), np.expand_dims(orientation, 0), np.expand_dims(distance, 0), np.expand_dims(velocity, 0)])
            class_channel = preds[:, pred_index]


        # This is the gradient of the output neuron (top predicted or chosen)
        # with regard to the output feature map of the last conv layer
        grads = tape.gradient(class_channel, last_conv_layer_output)


        # This is a vector where each entry is the mean intensity of the gradient
        # over a specific feature map channel
        pooled_grads = tf.reduce_mean(grads, axis=(0, 1))


        # We multiply each channel in the feature map array
        # by "how important this channel is" with regard to the top predicted class
        # then sum all the channels to obtain the heatmap class activation
        last_conv_layer_output = last_conv_layer_output[0]
        heatmap = last_conv_layer_output @ pooled_grads[..., tf.newaxis]
        heatmap = tf.squeeze(heatmap)

        # For visualization purpose, we will also normalize the heatmap between 0 & 1
        heatmap = tf.maximum(heatmap, 0) / tf.math.reduce_max(heatmap)
        return (preds, heatmap.numpy())

    def create_perception_model(self):
        layer_name = 'body_lidar-dense'
        proximity_predictions = Dense(3, activation='softmax')(self._model.get_layer(layer_name).output)
        self._perception_model = keras.Model([self._model.inputs],[proximity_predictions])
        self._perception_model.compile(optimizer='adam', loss='sparse_categorical_crossentropy')
        print(self._perception_model.summary())

    def make_proximity_prediction(self, s):
        laser = np.array([np.array(s[i][0]) for i in range(0, len(s))]).swapaxes(0, 1)
        orientation = np.array([np.array(s[i][1]) for i in range(0, len(s))]).swapaxes(0, 1)
        distance = np.array([np.array(s[i][2]) for i in range(0, len(s))]).swapaxes(0, 1)
        velocity = np.array([np.array(s[i][3]) for i in range(0, len(s))]).swapaxes(0, 1)

        proximity_categories = self._perception_model([np.expand_dims(laser, axis=0), np.expand_dims(orientation, axis=0), np.expand_dims(distance, axis=0), np.expand_dims(velocity, axis=0)])
        #
        # proximity_categories = proximityFunc(tf.convert_to_tensor(np.expand_dims(laser, axis=0), dtype='float64'),
        #                                     tf.convert_to_tensor(np.expand_dims(orientation, axis=0), dtype='float64'),
        #                                     tf.convert_to_tensor(np.expand_dims(distance, axis=0), dtype='float64'),
        #                                     tf.convert_to_tensor(np.expand_dims(velocity, axis=0), dtype='float64'))
        return proximity_categories

    def train_perception(self, states, proximity_categories):
        inputsL = np.array([])
        inputsO = np.array([])
        inputsD = np.array([])
        inputsV = np.array([])
        inputs = np.array([])
        for i, s in enumerate(states):
            laser = np.array([np.array(s[i][0]).astype('float32') for i in range(0, len(s))]).swapaxes(0, 1)
            orientation = np.array([np.array(s[i][1]).astype('float32') for i in range(0, len(s))]).swapaxes(0, 1)
            distance = np.array([np.array(s[i][2]).astype('float32') for i in range(0, len(s))]).swapaxes(0, 1)
            velocity = np.array([np.array(s[i][3]).astype('float32') for i in range(0, len(s))]).swapaxes(0, 1)

            if i == 0:
                inputsL = np.array([laser])
                inputsO = np.array([orientation])
                inputsD = np.array([distance])
                inputsV = np.array([velocity])
            else:
                # inputs = np.append(inputs, np.array([laser, orientation, distance, velocity]))
                inputsL = np.append(inputsL, np.expand_dims(laser, axis=0), axis=0)
                inputsO = np.append(inputsO, np.expand_dims(orientation, axis=0), axis=0)
                inputsD = np.append(inputsD, np.expand_dims(distance, axis=0), axis=0)
                inputsV = np.append(inputsV, np.expand_dims(velocity, axis=0), axis=0)

        proximity_categories = np.asarray(proximity_categories)
        self._perception_model.fit([inputsL, inputsO, inputsD, inputsV], proximity_categories, shuffle=True)

