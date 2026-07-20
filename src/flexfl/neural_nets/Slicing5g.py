from flexfl.builtins.NeuralNetworkABC import NeuralNetworkABC

class Slicing5g(NeuralNetworkABC):

    def keras_model(self, data_name, input_shape, output_size, is_classification):
        import keras
        layers = [
            keras.layers.Input(shape=input_shape),
            keras.layers.Dense(32, activation='relu'),
            keras.layers.Dense(32, activation='relu'),
            keras.layers.Dropout(0.1),
            keras.layers.Dense(output_size)
        ]
        if is_classification:
            layers.append(keras.layers.Softmax())
        return keras.models.Sequential(layers)


    def tf_model(self, data_name, input_shape, output_size, is_classification):
        import tensorflow as tf
        layers = [
            tf.keras.layers.Input(shape=input_shape),
            tf.keras.layers.Dense(32, activation='relu'),
            tf.keras.layers.Dense(32, activation='relu'),
            tf.keras.layers.Dropout(0.1),
            tf.keras.layers.Dense(output_size)
        ]
        if is_classification:
            layers.append(tf.keras.layers.Softmax())
        return tf.keras.models.Sequential(layers)


    def torch_model(self, data_name, input_shape, output_size, is_classification):
        import torch.nn as nn
        layers = [
            nn.Linear(input_shape[0], 32),
            nn.ReLU(),
            nn.Linear(32, 32),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(32, output_size)
        ]
        return nn.Sequential(*layers)