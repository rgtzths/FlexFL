import tensorflow as tf

from ML.MLUtils import MLUtils

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
    def __init__(self,
        optimizer,
        loss,
        learning_rate,
        **kwargs
    ):
        prefix = 'tf'
        optimizer = OPTIMIZERS[optimizer](learning_rate=learning_rate)
        loss = LOSSES[loss]()
        super().__init__(prefix, optimizer, loss, **kwargs)
        
