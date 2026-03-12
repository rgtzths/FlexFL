from flexfl.builtins.NeuralNetworkABC import NeuralNetworkABC

class Slicing5g(NeuralNetworkABC):

    def keras_model(self, input_shape, output_size, is_classification):
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