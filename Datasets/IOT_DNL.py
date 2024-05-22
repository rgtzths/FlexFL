from kaggle import api
import pandas as pd
from sklearn.preprocessing import StandardScaler
import numpy as np

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
        self.metadata['classes'] = len(np.unique(y))
        self.save_features(x.columns)
        self.split_save(x, y, val_size, test_size, StandardScaler())