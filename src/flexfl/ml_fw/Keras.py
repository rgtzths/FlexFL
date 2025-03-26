import numpy as np
from itertools import cycle
import keras
import tensorflow as tf

from flexfl.builtins.MLFrameworkABC import MLFrameworkABC


OPTIMIZERS: dict[str, keras.optimizers.Optimizer] = {
    'adam': keras.optimizers.Adam,
    'sgd': keras.optimizers.SGD,
    'rmsprop': keras.optimizers.RMSprop,
}

LOSSES: dict[str, keras.losses.Loss] = {
    'mse': keras.losses.MeanSquaredError,
    'mae': keras.losses.MeanAbsoluteError,
    'mape': keras.losses.MeanAbsolutePercentageError,
    'scc': keras.losses.SparseCategoricalCrossentropy,
}

class Keras(MLFrameworkABC):


    def __init__(self, *,
        backend: str = "tensorflow",
        **kwargs
    ) -> None:
        self.backend = backend
        super().__init__(**kwargs)


    @property
    def prefix(self) -> str:
        return "keras"
    

    def set_seed(self, seed: int):
        if self.backend == "tensorflow":
            tf.random.set_seed(seed)
        elif self.backend == "torch":
            import torch
            torch.manual_seed(seed)
    

    def setup(self):
        self.model: keras.Model = self.model
        self.optimizer: keras.optimizers.Optimizer = OPTIMIZERS[self.optimizer_name](learning_rate=self.learning_rate)
        self.loss: keras.losses.Loss = LOSSES[self.loss_name]()
        self.model.compile(optimizer=self.optimizer, loss=self.loss)


    def load_data(self, split: str):
        x, y = self.dataset.load_data(split, loader="tf")
        x: tf.data.Dataset = x.batch(self.batch_size)
        y_: tf.data.Dataset = tf.data.Dataset.from_tensor_slices(y).batch(self.batch_size)
        data = tf.data.Dataset.zip((x, y_))
        self.n_samples = y.shape[0]
        setattr(self, f"x_{split}", x)
        setattr(self, f"y_{split}", y)
        setattr(self, f"{split}_data", data)
        setattr(self, f"{split}_iterator", cycle(data))
        

    def get_weights(self) -> np.ndarray:
        weights = self.model.get_weights()
        return np.concatenate([w.flatten() for w in weights])
    

    def set_weights(self, weights: np.ndarray):
        start = 0
        new_weights = []
        for w in self.model.get_weights():
            size = np.prod(w.shape)
            new_weights.append(weights[start:start + size].reshape(w.shape))
            start += size
        self.model.set_weights(new_weights)


    def calculate_gradients(self) -> np.ndarray:
        if self.backend != "tensorflow":
            raise NotImplementedError
        x, y = next(self.train_iterator)
        with tf.GradientTape() as tape:
            y_pred = self.model(x)
            loss = self.loss(y, y_pred)
        gradients = tape.gradient(loss, self.model.trainable_variables)
        gradient_arrays = [g.numpy().flatten() for g in gradients]
        return np.concatenate(gradient_arrays)


    def apply_gradients(self, gradients: np.ndarray):
        if self.backend != "tensorflow":
            raise NotImplementedError
        start = 0
        gradient_tensors = []
        for param in self.model.trainable_variables:
            size = np.prod(param.shape)
            grad_tensor = tf.constant(gradients[start:start + size].reshape(param.shape), dtype=tf.float32)
            gradient_tensors.append(grad_tensor)
            start += size
        gradient_vars = zip(gradient_tensors, self.model.trainable_variables)
        self.optimizer.apply_gradients(gradient_vars)


    def train(self, epochs: int, verbose=False):
        self.model.fit(
            self.train_data,
            epochs=epochs,
            verbose=1 if verbose else 0
        )


    def predict(self, data):
        return self.model.predict(data, batch_size=self.batch_size, verbose=0)
    

    def calculate_loss(self, y_true: np.ndarray, y_pred: np.ndarray) -> float:
        return float(self.loss(y_true, y_pred))
    

    def save_model(self, path):
        self.model.save(f"{path}.keras")


    def load_model(self, path):
        self.model = keras.models.load_model(f"{path}.keras")