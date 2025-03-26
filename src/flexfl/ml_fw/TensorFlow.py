import tensorflow as tf
import numpy as np
from itertools import cycle

from flexfl.builtins.MLFrameworkABC import MLFrameworkABC

OPTIMIZERS = {
    'adam': tf.keras.optimizers.Adam,
    'sgd': tf.keras.optimizers.SGD,
    'rmsprop': tf.keras.optimizers.RMSprop,
}

LOSSES = {
    'mse': tf.keras.losses.MeanSquaredError,
    'mae': tf.keras.losses.MeanAbsoluteError,
    'mape': tf.keras.losses.MeanAbsolutePercentageError,
    'scc': tf.keras.losses.SparseCategoricalCrossentropy,
}


class TensorFlow(MLFrameworkABC):


    @property
    def prefix(self) -> str:
        return "tf"
    

    def set_seed(self, seed: int):
        tf.random.set_seed(seed)
    

    def setup(self):
        self.optimizer = OPTIMIZERS[self.optimizer_name](learning_rate=self.learning_rate)
        self.loss = LOSSES[self.loss_name]()
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


    def get_weights(self):
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

    
    def calculate_gradients(self):
        x, y = next(self.train_iterator)
        with tf.GradientTape() as tape:
            y_pred = self.model(x)
            loss = self.loss(y, y_pred)
        gradients = tape.gradient(loss, self.model.trainable_variables)
        gradient_arrays = [g.numpy().flatten() for g in gradients]
        return np.concatenate(gradient_arrays)
    

    def apply_gradients(self, gradients: np.ndarray):
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
        return float(self.loss(y_true, y_pred).numpy())
    

    def save_model(self, path):
        self.model.save(f"{path}.keras")


    def load_model(self, path):
        self.model = tf.keras.models.load_model(f"{path}.keras")