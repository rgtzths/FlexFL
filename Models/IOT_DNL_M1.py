import tensorflow as tf

from Utils.ModelUtils import ModelUtils

class IOT_DNL_M1(ModelUtils):

    def tf_model(self, input_shape, classes):
        return tf.keras.models.Sequential([
            # input layer
            tf.keras.layers.Input(shape=input_shape),
            # hidden layers
            tf.keras.layers.Dense(64, activation='relu'),
            tf.keras.layers.Dropout(0.1),
            tf.keras.layers.Dense(64, activation='relu'),
            tf.keras.layers.Dropout(0.1),
            tf.keras.layers.Dense(64, activation='relu'),
            tf.keras.layers.Dropout(0.1),
            tf.keras.layers.Dense(64, activation='relu'),
            # output layer
            tf.keras.layers.Dense(classes, activation='softmax')
        ])