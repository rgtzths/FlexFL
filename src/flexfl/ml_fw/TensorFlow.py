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
    

    def setup(self):
        tf.random.set_seed(self.seed)
        self.optimizer = OPTIMIZERS[self.optimizer_name](learning_rate=self.learning_rate)
        self.loss = LOSSES[self.loss_name]()
        self.model.compile(optimizer=self.optimizer, loss=self.loss)


    def load_data(self, split: str):
        x, y = self.dataset.load_data(split)
        self.n_samples = x.shape[0]
        x_ = tf.data.Dataset.from_tensor_slices(x).batch(self.batch_size)
        data = tf.data.Dataset.from_tensor_slices((x, y)).batch(self.batch_size)
        setattr(self, f"x_{split}", x_)
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

    
    def get_gradients(self):
        with tf.GradientTape() as tape:
            x, y = next(self.train_iterator)
            y_pred = self.model(x, training=True)
            loss = self.loss(y, y_pred)
        gradients = tape.gradient(loss, self.model.trainable_variables)
        return np.concatenate([g.numpy().flatten() for g in gradients])
    

    def apply_gradients(self, gradients: np.ndarray):
        start = 0
        grads_list = []
        trainable_vars = self.model.trainable_variables
        for var in trainable_vars:
            size = np.prod(var.shape)
            grads_list.append(tf.convert_to_tensor(gradients[start:start + size].reshape(var.shape)))
            start += size
        self.optimizer.apply_gradients(zip(grads_list, trainable_vars))

    
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