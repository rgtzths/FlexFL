from flexfl.builtins.NeuralNetworkABC import NeuralNetworkABC

class UNSW(NeuralNetworkABC):

    def keras_model(self, data_name, input_shape, output_size, is_classification):
        import keras
        layers = [
            keras.layers.Input(shape=input_shape),
            keras.layers.Dense(300, activation='relu'),
            keras.layers.Dense(100, activation='relu'),
            keras.layers.Dense(40, activation='relu'),
            keras.layers.Dense(output_size)
        ]
        if is_classification:
            layers.append(keras.layers.Softmax())
        return keras.models.Sequential(layers)


    def tf_model(self, data_name, input_shape, output_size, is_classification):
        import tensorflow as tf
        layers = [
            tf.keras.layers.Input(shape=input_shape),
            tf.keras.layers.Dense(300, activation='relu'),
            tf.keras.layers.Dense(100, activation='relu'),
            tf.keras.layers.Dense(40, activation='relu'),
            tf.keras.layers.Dense(output_size)
        ]
        if is_classification:
            layers.append(tf.keras.layers.Softmax())
        return tf.keras.models.Sequential(layers)


    def torch_model(self, data_name, input_shape, output_size, is_classification):
        import torch.nn as nn
        layers = [
            nn.Linear(input_shape[0], 300),
            nn.ReLU(),
            nn.Linear(300, 100),
            nn.ReLU(),
            nn.Linear(100, 40),
            nn.ReLU(),
            nn.Linear(40, output_size)
        ]
        return nn.Sequential(*layers)


# "UNSW": "Evaluation of Adversarial Training on Different Types of Neural Networks in Deep Learning-based IDSs - (table II)",
# keras.layers.Dense(128, activation='relu'),
# keras.layers.Dense(96, activation='relu'),
# keras.layers.Dense(64, activation='relu'),
# keras.layers.Dropout(0.25),
