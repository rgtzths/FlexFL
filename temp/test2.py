import os
BACKEND = "torch"
os.environ["KERAS_BACKEND"] = BACKEND
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
import keras
import tensorflow as tf
import numpy as np
from itertools import cycle


def get_gradients(model: keras.Model, train_iterator, loss: keras.losses.Loss):
    with tf.GradientTape() as tape:
        x, y = next(train_iterator)
        y_pred = model(x, training=True)
        loss = loss(y, y_pred)
    gradients = tape.gradient(loss, model.trainable_variables)
    return np.concatenate([g.numpy().flatten() for g in gradients])

def apply_gradients(gradients: np.ndarray, model, optimizer):
    start = 0
    grads_list = []
    trainable_vars = model.trainable_variables
    for var in trainable_vars:
        size = np.prod(var.shape)
        grads_list.append(tf.convert_to_tensor(gradients[start:start + size].reshape(var.shape)))
        start += size
    optimizer.apply_gradients(zip(grads_list, trainable_vars))



model = keras.models.Sequential([
    keras.layers.Input(shape=(11,)),
    keras.layers.Dense(64, activation='relu'),
    keras.layers.Dropout(0.1),
    keras.layers.Dense(64, activation='relu'),
    keras.layers.Dropout(0.1),
    keras.layers.Dense(64, activation='relu'),
    keras.layers.Dropout(0.1),
    keras.layers.Dense(64, activation='relu'),
    keras.layers.Dense(6)
])

x = np.load("data/IOT_DNL/node_1/x_train.npy")
y = np.load("data/IOT_DNL/node_1/y_train.npy")
train_data = tf.data.Dataset.from_tensor_slices((x, y)).batch(32)
train_iterator = cycle(train_data)

# sparse cate
loss = keras.losses.SparseCategoricalCrossentropy()
optimizer = keras.optimizers.Adam()


for i in range(10):
    gradients = get_gradients(model, train_iterator, loss)
    print("Gradients calculated")
    apply_gradients(gradients, model, optimizer)
    print(f"Epoch {i+1} done")
