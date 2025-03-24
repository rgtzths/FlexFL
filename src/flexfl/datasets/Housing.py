from sklearn.preprocessing import StandardScaler
from sklearn.datasets import fetch_california_housing

from flexfl.builtins.DatasetABC import DatasetABC


class Housing(DatasetABC):

    @property
    def is_classification(self) -> bool:
        return False
    

    @property
    def scaler(self):
        return StandardScaler


    def download(self):
        return

    
    def preprocess(self, val_size, test_size):
        x, y = fetch_california_housing(return_X_y=True)
        self.split_save(x, y, val_size, test_size)