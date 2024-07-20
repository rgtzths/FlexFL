import tensorflow as tf

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
    
    
    def init(self):
        self.prefix = 'tf'
        self.loss = LOSSES[self.loss]()
        self.optimizer = OPTIMIZERS[self.optimizer](learning_rate=self.learning_rate)


    def load_data(self, split):
        x, y = self.dataset.load_data(split)
        data = tf.data.Dataset.from_tensor_slices((x, y)).batch(self.batch_size)
        setattr(self, f"{split}_data", data)


    def load_worker_data(self, worker_id, num_workers):
        x, y = self.dataset.load_worker_data(worker_id, num_workers)
        self.my_data = tf.data.Dataset.from_tensor_slices((x, y)).batch(self.batch_size)


    def compile_model(self):
        self.model.compile(optimizer=self.optimizer, loss=self.loss, metrics=['accuracy'])
        
    
    def get_weights(self):
        return self.model.get_weights()
    

    def set_weights(self, weights):
        self.model.set_weights(weights)


    def get_gradients(self):
        ...


    def apply_gradients(self, gradients):
        ...


    def train(self, epochs):
        self.model.fit(
            self.my_data,
            epochs=epochs,
            verbose=0
        )


    def evaluate(self, split):
        return self.model.evaluate(getattr(self, f"{split}_data"))
    

    def save_model(self, path):
        self.model.save(path)


    def load_model(self, path):
        self.model = tf.keras.models.load_model(path)