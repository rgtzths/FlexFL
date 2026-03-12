from flexfl.builtins.NeuralNetworkABC import NeuralNetworkABC

class IOT_DNL(NeuralNetworkABC):

    def keras_model(self, input_shape, output_size, is_classification):
        import keras
        layers = [
            keras.layers.Input(shape=input_shape),
            keras.layers.Dense(64, activation='relu'),
            keras.layers.Dropout(0.1),
            keras.layers.Dense(64, activation='relu'),
            keras.layers.Dropout(0.1),
            keras.layers.Dense(64, activation='relu'),
            keras.layers.Dropout(0.1),
            keras.layers.Dense(64, activation='relu'),
            keras.layers.Dense(output_size)
        ]
        if is_classification:
            layers.append(keras.layers.Softmax())
        return keras.models.Sequential(layers)

        
    def tf_model(self, input_shape, output_size, is_classification):
        import tensorflow as tf
        layers = [
            tf.keras.layers.Input(shape=input_shape),
            tf.keras.layers.Dense(64, activation='relu'),
            tf.keras.layers.Dropout(0.1),
            tf.keras.layers.Dense(64, activation='relu'),
            tf.keras.layers.Dropout(0.1),
            tf.keras.layers.Dense(64, activation='relu'),
            tf.keras.layers.Dropout(0.1),
            tf.keras.layers.Dense(64, activation='relu'),
            tf.keras.layers.Dense(output_size)
        ]
        if is_classification:
            layers.append(tf.keras.layers.Softmax())
        return tf.keras.models.Sequential(layers)
    

    def torch_model(self, input_shape, output_size, is_classification):
        import torch.nn as nn
        layers = [
            nn.Linear(input_shape[0], 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 64),
            nn.ReLU(),
            nn.Linear(64, output_size)
        ]
        if is_classification:
            layers.append(nn.Softmax(dim=1))
        return nn.Sequential(*layers)