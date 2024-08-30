import tensorflow as tf
import torch.nn as nn
import torch.nn.functional as F

from Utils.ModelUtils import ModelUtils

class IOT_DNL_M1(ModelUtils):

    def tf_model(self, input_shape, classes):
        return tf.keras.models.Sequential([
            # input layer
            tf.keras.layers.Input(shape=input_shape),
            # hidden layers
            tf.keras.layers.Dense(64, activation='relu'),
            tf.keras.layers.Dropout(0.1),
            tf.keras.layers.Dense(64, activation='relu'),
            tf.keras.layers.Dropout(0.1),
            tf.keras.layers.Dense(64, activation='relu'),
            tf.keras.layers.Dropout(0.1),
            tf.keras.layers.Dense(64, activation='relu'),
            # output layer
            tf.keras.layers.Dense(classes, activation='softmax')
        ])
    

    def torch_model(self, input_shape, classes):

        # TODO: this configuration is just an example for testing!
        class Net(nn.Module):
            def __init__(self):
                super(Net, self).__init__()
                self.flatten = nn.Flatten()
                self.fc1 = nn.Linear(11, 64)
                self.fc2 = nn.Linear(64, 64)
                self.fc3 = nn.Linear(64, 64)
                self.fc4 = nn.Linear(64, 64)
                self.output = nn.Linear(64, 6)
                self.dropout = nn.Dropout(0.1)

            def forward(self, x):
                x = self.flatten(x)
                x = F.relu(self.fc1(x))
                x = self.dropout(x)
                x = F.relu(self.fc2(x))
                x = self.dropout(x)
                x = F.relu(self.fc3(x))
                x = self.dropout(x)
                x = F.relu(self.fc4(x))
                x = self.output(x)
                x = F.softmax(x, dim=1)
                return x

        return Net()