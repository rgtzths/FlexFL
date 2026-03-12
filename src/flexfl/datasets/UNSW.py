import pandas as pd
from sklearn.preprocessing import StandardScaler

from flexfl.builtins.DatasetABC import DatasetABC


class UNSW(DatasetABC):

    @property
    def is_classification(self) -> bool:
        return True
    

    @property
    def scaler(self):
        return StandardScaler


    def download(self):
        import kaggle
        kaggle.api.dataset_download_files(
            "sankurisrinath/nf-unsw-nb15-v2csv",
            path=f"{self.default_folder}",
            quiet=False,
            unzip=True
        )

    
    def preprocess(self, val_size, test_size):
        data = pd.read_csv(f"{self.default_folder}/NF-UNSW-NB15-v2.csv")
        data.dropna()
        y = data['Label'].astype(int)
        x = data.drop(columns=['Label', "IPV4_SRC_ADDR", "L4_SRC_PORT", "IPV4_DST_ADDR", "L4_DST_PORT", "Attack"])
        self.save_features(x.columns)
        self.split_save(x, y, val_size, test_size)