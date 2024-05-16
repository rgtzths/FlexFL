from tensorflow.keras.datasets import fashion_mnist
import numpy as np

from Utils.DatasetUtils import DatasetUtils

class FASHION(DatasetUtils):

    def download(self):
        return


    def preprocess(self, val_size, test_size):
        (x_train, y_train), (x_test, y_test) = fashion_mnist.load_data()
        x = np.concatenate((x_train, x_test))
        y = np.concatenate((y_train, y_test))
        x = x.astype('float32')
        x = x / 255.0
        self.split_save(x, y, val_size, test_size)