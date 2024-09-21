import tensorflow as tf
import numpy as np

from Utils.MLUtils import MLUtils

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

class Tensorflow(MLUtils):
    
    
    def setup(self):
        self.prefix = 'tf'
        self.loss = LOSSES[self.loss]()
        self.optimizer = OPTIMIZERS[self.optimizer](learning_rate=self.learning_rate)


    def load_data(self, split):
        x, y = self.dataset.load_data(split)
        data = tf.data.Dataset.from_tensor_slices((x, y)).batch(self.batch_size)
        setattr(self, f"{split}_data", data)
        return x, y


    def load_worker_data(self, worker_id, num_workers):
        x, y = self.dataset.load_worker_data(worker_id, num_workers)
        self.my_data = tf.data.Dataset.from_tensor_slices((x, y)).batch(self.batch_size)
        self.my_iterator = iter(self.my_data)
        return x, y


    def compile_model(self):
        self.model.compile(optimizer=self.optimizer, loss=self.loss, metrics=['accuracy'])
        
    
    def get_weights(self):
        return self.model.get_weights()
    

    def set_weights(self, weights):
        self.model.set_weights(weights)


    def get_gradients(self):
        with tf.GradientTape() as tape:
            try:
                x, y = next(self.my_iterator)
            except StopIteration:
                self.my_iterator = iter(self.my_data)
                x, y = next(self.my_iterator)
            y_pred = self.model(x, training=True)
            loss = self.loss(y, y_pred)
        return tape.gradient(loss, self.model.trainable_variables)


    def apply_gradients(self, gradients):
        self.optimizer.apply_gradients(zip(gradients, self.model.trainable_variables))


    def train(self, epochs):
        self.model.fit(
            self.my_data,
            epochs=epochs,
            verbose=0
        )


    def predict(self, data):
        return self.model.predict(data, verbose=0)
    

    def save_model(self, path):
        self.model.save(f"{path}.keras")


    def load_model(self, path):
        self.model = tf.keras.models.load_model(f"{path}.keras")