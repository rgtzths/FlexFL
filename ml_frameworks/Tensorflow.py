import tensorflow as tf
import numpy as np
from itertools import cycle

from my_builtins.MLFrameworkABC import MLFrameworkABC

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


class Tensorflow(MLFrameworkABC):


    @property
    def prefix(self) -> str:
        return "tf"
    

    def setup(self):
        tf.random.set_seed(self.seed)
        self.optimizer = OPTIMIZERS[self.optimizer_name](learning_rate=self.learning_rate)
        self.loss = LOSSES[self.loss_name]()


    def load_data(self, split: str) -> None:
        x, y = self.dataset.load_data(split)
        data = tf.data.Dataset.from_tensor_slices((x, y)).batch(self.batch_size)
        setattr(self, f"{split}_data", data)
        self.n_samples = x.shape[0]


    def load_worker_data(self, worker_id: int, num_workers: int) -> None:
        x, y = self.dataset.load_worker_data(worker_id, num_workers)
        self.my_data = tf.data.Dataset.from_tensor_slices((x, y)).batch(self.batch_size)
        self.my_iterator = cycle(self.my_data)
        self.n_samples = x.shape[0]


    def compile_model(self):
        self.model.compile(optimizer=self.optimizer, loss=self.loss)


    def get_weights(self) -> np.array:
        weights = self.model.get_weights()
        return np.concatenate([w.flatten() for w in weights])
    

    def set_weights(self, weights: np.array) -> None:
        start = 0
        new_weights = []
        for w in self.model.get_weights():
            size = np.prod(w.shape)
            new_weights.append(weights[start:start + size].reshape(w.shape))
            start += size
        self.model.set_weights(new_weights)

    
    def get_gradients(self) -> np.array:
        with tf.GradientTape() as tape:
            x, y = next(self.my_iterator)
            y_pred = self.model(x, training=True)
            loss = self.loss(y, y_pred)
        gradients = tape.gradient(loss, self.model.trainable_variables)
        return np.concatenate([g.numpy().flatten() for g in gradients])
    

    def apply_gradients(self, gradients: np.array) -> None:
        start = 0
        grads_list = []
        trainable_vars = self.model.trainable_variables
        for var in trainable_vars:
            size = np.prod(var.shape)
            grads_list.append(tf.convert_to_tensor(gradients[start:start + size].reshape(var.shape)))
            start += size
        self.optimizer.apply_gradients(zip(grads_list, trainable_vars))

    
    def train(self, epochs: int) -> None:
        self.model.fit(
            self.my_data,
            epochs=epochs,
            verbose=0
        )

    
    def predict(self, data):
        return self.model.predict(data, batch_size=self.batch_size)
    

    def save_model(self, path):
        self.model.save(f"{path}.keras")


    def load_model(self, path):
        self.model = tf.keras.models.load_model(f"{path}.keras")