from kaggle import api
import pandas as pd
from sklearn.preprocessing import StandardScaler
import tensorflow as tf

from Utils.DatasetUtils import DatasetUtils

class IOT_DNL(DatasetUtils):
    
    def download(self):
        api.dataset_download_files(
            "speedwall10/iot-device-network-logs",
            path=f"Data/{self.name}",
            quiet=False,
            unzip=True
        )


    def preprocess(self, val_size, test_size):
        data = pd.read_csv(f"Data/{self.name}/Preprocessed_data.csv")
        data.dropna()
        x = data.drop('normality', axis=1)
        x = x.drop('frame.number', axis=1)
        x = x.drop('frame.time', axis=1)
        y = data['normality']
        self.save_features(x.columns)
        self.split_save(x, y, val_size, test_size, StandardScaler())


    def tf_model(self):
        return tf.keras.models.Sequential([
            # flatten layer
            tf.keras.layers.Flatten(input_shape=(11,)),
            # hidden layers
            tf.keras.layers.Dense(64, activation='relu'),
            tf.keras.layers.Dropout(0.1),
            tf.keras.layers.Dense(64, activation='relu'),
            tf.keras.layers.Dropout(0.1),
            tf.keras.layers.Dense(64, activation='relu'),
            tf.keras.layers.Dropout(0.1),
            tf.keras.layers.Dense(64, activation='relu'),
            # output layer
            tf.keras.layers.Dense(6, activation='softmax')
        ])