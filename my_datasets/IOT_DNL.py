import kaggle
import pandas as pd
from sklearn.preprocessing import StandardScaler

from utils.DatasetABC import DatasetABC, DATA_FOLDER


class IOT_DNL(DatasetABC):

    @property
    def is_classification(self) -> bool:
        return True
    

    @property
    def input_shape(self) -> tuple[int]:
        return (11,)
    

    @property
    def output_shape(self) -> tuple[int]:
        return (6,)


    def download(self):
        kaggle.api.dataset_download_files(
            "speedwall10/iot-device-network-logs",
            path=f"{DATA_FOLDER}/{self.name}",
            quiet=False,
            unzip=True
        )

    
    def preprocess(self, val_size, test_size):
        data = pd.read_csv(f"{DATA_FOLDER}/{self.name}/Preprocessed_data.csv")
        data.dropna()
        x = data.drop('normality', axis=1)
        x = x.drop('frame.number', axis=1)
        x = x.drop('frame.time', axis=1)
        y = data['normality']
        self.save_features(x.columns)
        self.split_save(x, y, val_size, test_size, StandardScaler())