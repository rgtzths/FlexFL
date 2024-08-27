import tensorflow as tf
import torch.nn as nn

from Utils.ModelUtils import ModelUtils

class CIFAR10_M1(ModelUtils):

    def tf_model(self, input_shape, classes):
        return tf.keras.models.Sequential([
            tf.keras.layers.Conv2D(32, (3, 3), activation='relu', input_shape=input_shape),
            tf.keras.layers.Conv2D(32, (3, 3), activation='relu'),
            tf.keras.layers.MaxPooling2D((2, 2)),
            tf.keras.layers.Dropout(0.25),
            tf.keras.layers.Conv2D(64, (3, 3), activation='relu', padding='same'),
            tf.keras.layers.Conv2D(64, (3, 3), activation='relu'),
            tf.keras.layers.MaxPooling2D((2, 2)),
            tf.keras.layers.Dropout(0.25),
            tf.keras.layers.Conv2D(128, (3, 3), activation='relu', padding='same'),
            tf.keras.layers.Conv2D(128, (3, 3), activation='relu'),
            tf.keras.layers.MaxPooling2D((2, 2)),
            tf.keras.layers.Dropout(0.25),
            tf.keras.layers.Flatten(),
            tf.keras.layers.Dense(1024, activation=tf.keras.layers.LeakyReLU()),
            tf.keras.layers.Dense(512, activation=tf.keras.layers.LeakyReLU()),
            tf.keras.layers.Dense(classes, activation='softmax')
        ])
        

    def torch_model(self, input_shape, classes):

        # TODO: this configuration is just an example for testing!
        class Net(nn.Module):
            def __init__(self):
                super(Net, self).__init__()
                self.conv1 = nn.Conv2d(3, 6, 5)
                self.pool1 = nn.MaxPool2d(2, 2)
                self.pool2 = nn.MaxPool2d(2, 2)
                self.conv2 = nn.Conv2d(6, 16, 5)
                self.fc1 = nn.Linear(16 * 5 * 5, 120)
                self.fc2 = nn.Linear(120, 84)
                self.fc3 = nn.Linear(84, 10)
                self.relu1 = nn.ReLU()
                self.relu2 = nn.ReLU()
                self.relu3 = nn.ReLU()
                self.relu4 = nn.ReLU()

            def forward(self, x):
                x = self.pool1(self.relu1(self.conv1(x)))
                x = self.pool2(self.relu2(self.conv2(x)))
                x = x.view(-1, 16 * 5 * 5)
                x = self.relu3(self.fc1(x))
                x = self.relu4(self.fc2(x))
                x = self.fc3(x)
                return x

        return Net()