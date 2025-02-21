from my_builtins.NeuralNetworkABC import NeuralNetworkABC

class IOT_DNL(NeuralNetworkABC):
        
    def tf_model(self, input_shape, output_shape):
        import tensorflow as tf
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
            tf.keras.layers.Dense(output_shape[0], activation='softmax')
        ])