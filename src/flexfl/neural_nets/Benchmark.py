import json
from pathlib import Path

from flexfl.builtins.NeuralNetworkABC import NeuralNetworkABC

CONFIGS_DIR = Path(__file__).parent.parent.parent.parent / "results/hyperparameter_optimization"


class Benchmark(NeuralNetworkABC):

    def _load(self, data_name: str) -> tuple[list[int], float]:
        path = CONFIGS_DIR / f"{data_name}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"No hyperparameter config for '{data_name}'. "
                f"Run src/other/model_finder.py for this dataset first. "
                f"Expected: {path}"
            )
        with open(path) as f:
            config = json.load(f)
        units = [config[f"n_units_l{i}"] for i in range(config["n_layers"])]
        return units, config["weight_decay"]

    def keras_model(self, data_name, input_shape, output_size, is_classification):
        import keras
        units, wd = self._load(data_name)
        layers = [keras.layers.Input(shape=input_shape)]
        for u in units:
            layers.append(keras.layers.Dense(u, activation='relu', kernel_regularizer=keras.regularizers.L2(wd)))
        layers.append(keras.layers.Dense(output_size))
        if is_classification:
            layers.append(keras.layers.Softmax())
        return keras.models.Sequential(layers)

    def tf_model(self, data_name, input_shape, output_size, is_classification):
        import tensorflow as tf
        units, wd = self._load(data_name)
        layers = [tf.keras.layers.Input(shape=input_shape)]
        for u in units:
            layers.append(tf.keras.layers.Dense(u, activation='relu', kernel_regularizer=tf.keras.regularizers.L2(wd)))
        layers.append(tf.keras.layers.Dense(output_size))
        if is_classification:
            layers.append(tf.keras.layers.Softmax())
        return tf.keras.models.Sequential(layers)

    def torch_model(self, data_name, input_shape, output_size, is_classification):
        import torch.nn as nn
        units, wd = self._load(data_name)
        sizes = [input_shape[0]] + units + [output_size]
        layers = []
        for i in range(len(sizes) - 2):
            layers.append(nn.Linear(sizes[i], sizes[i + 1]))
            layers.append(nn.ReLU())
        layers.append(nn.Linear(sizes[-2], sizes[-1]))
        model = nn.Sequential(*layers)
        model._weight_decay = wd
        return model
