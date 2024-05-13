from kaggle import api
from pathlib import Path
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import tensorflow as tf

from Datasets.DatasetUtils import DatasetUtils

class IOT_DNL(DatasetUtils):

    def __init__(self):
        super().__init__()

    
    def download(self):
        api.dataset_download_files(
            "speedwall10/iot-device-network-logs",
            path=f"Data/{self.name}",
            quiet=False,
            unzip=True
        )


    def preprocess(self):
        dataset = f"Data/{self.name}/Preprocessed_data.csv"

        data = pd.read_csv(dataset)
        data.dropna()
        X = data.drop('normality', axis=1)
        X = X.drop('frame.number', axis=1)
        X = X.drop('frame.time', axis=1)
        y = data['normality']
        n_samples=X.shape[0]

        x_train, x_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, shuffle=True)
        scaler = StandardScaler()
        x_train = pd.DataFrame(scaler.fit_transform(x_train), columns=x_train.columns)
        x_test = pd.DataFrame(scaler.transform(x_test), columns=x_test.columns)
        x_train, x_val, y_train, y_val = train_test_split(x_train, y_train, test_size=0.2, random_state=42, shuffle=True)

        print(f"\nTotal samples {n_samples}")
        print(f"Shape of the train data: {x_train.shape}")
        print(f"Shape of the validation data: {x_val.shape}")
        print(f"Shape of the test data: {x_test.shape}\n")
        self.metadata['samples'] = n_samples
        self.metadata['features'] = X.columns.tolist()
        self.metadata['split'] = {
            'train': x_train.shape[0],
            'val': x_val.shape[0],
            'test': x_test.shape[0]
        }
        self.save_metadata()

        self.save_data(x_train, y_train, 'train')
        self.save_data(x_val, y_val, 'val')
        self.save_data(x_test, y_test, 'test')


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