import tensorflow as tf

from Utils.ModelUtils import ModelUtils

class IOT_DNL(ModelUtils):

    def tf_model(self, input_shape, classes):
        return tf.keras.models.Sequential([
            # flatten layer
            tf.keras.layers.Flatten(input_shape=input_shape),
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