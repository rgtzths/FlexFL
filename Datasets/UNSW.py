from kaggle import api
from sklearn.preprocessing import QuantileTransformer
import pandas as pd
from sklearn.model_selection import train_test_split
import numpy as np

from Utils.DatasetUtils import DatasetUtils

class UNSW(DatasetUtils):

    def download(self):
        api.dataset_download_files(
            "sankurisrinath/nf-unsw-nb15-v2csv",
            path=f"Data/{self.name}",
            quiet=False,
            unzip=True
        )


    def preprocess(self, val_size, test_size):
        dataset = f"Data/{self.name}/NF-UNSW-NB15-v2.csv"
        data = pd.read_csv(dataset)
        data.dropna()
        y = data['Label']
        x = data.drop(columns=['Label', "IPV4_SRC_ADDR", "L4_SRC_PORT", "IPV4_DST_ADDR", "L4_DST_PORT", "Attack"])
        self.save_features(x.columns)
        _, x, _, y = train_test_split(x, y, test_size=0.25, stratify=y, random_state=42)
        scaler = QuantileTransformer(output_distribution='normal')
        self.metadata['classes'] = len(np.unique(y))
        self.split_save(x, y, val_size, test_size, scaler)