from tensorflow.keras.datasets import mnist
import numpy as np

from Datasets.DatasetUtils import DatasetUtils

class MNIST(DatasetUtils):

    def download(self):
        return


    def preprocess(self, val_size, test_size):
        (x_train, y_train), (x_test, y_test) = mnist.load_data()
        x = np.concatenate((x_train, x_test))
        y = np.concatenate((y_train, y_test))
        x = x.astype('float32')
        x = x / 255.0
        self.split_save(x, y, val_size, test_size)