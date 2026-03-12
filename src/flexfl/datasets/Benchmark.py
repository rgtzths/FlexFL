from flexfl.builtins.DatasetABC import DatasetABC
from datasets import load_dataset
from sklearn.preprocessing import LabelEncoder

class MyScaler:

    def fit_transform(self, x):
        return x

    def transform(self, x):
        return x

class Benchmark(DatasetABC):

    def __init__(self, *, data_name:str = "clf_cat_albert", data_folder:str = None, **kwargs):
        self.class_task = True if "clf" in data_name else False

        super().__init__(data_name = data_name, data_folder=data_folder, **kwargs)


    @property
    def is_classification(self) -> bool:
        return self.class_task
    
    @property
    def scaler(self):
        return MyScaler


    def download(self):
        return

    
    def preprocess(self, val_size, test_size):
        ds = load_dataset("inria-soda/tabular-benchmark", self.name)["train"].to_pandas().values
        x = ds[:,:-1]
        y = ds[:,-1]
        if self.class_task:
            le = LabelEncoder()
            y = le.fit_transform(y)
        self.split_save(x, y, val_size, test_size)