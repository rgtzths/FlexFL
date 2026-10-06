import numpy as np
from datasets import load_dataset
from sklearn.preprocessing import LabelEncoder, StandardScaler

from flexfl.builtins.DatasetABC import DatasetABC

HF_DATASET = "inria-soda/tabular-benchmark"
HF_REVISION = "8d0ff9103525b7e3579b180230fddb3186258301"
SENTINEL = -999.0


def drop_sentinel_rows(x, y):
    keep = ~np.all(x == SENTINEL, axis=1)
    return x[keep], y[keep]


def is_clf(name):
    return name.startswith("clf_")


def load_raw(name, revision=HF_REVISION, keep_sentinel_rows=False):
    df = load_dataset(HF_DATASET, name, revision=revision)["train"].to_pandas()
    x = df.iloc[:, :-1].to_numpy(dtype=np.float64)
    y = df.iloc[:, -1].to_numpy()
    if not keep_sentinel_rows:
        x, y = drop_sentinel_rows(x, y)
    if is_clf(name):
        y = LabelEncoder().fit_transform(y)
    return x, y


class Benchmark(DatasetABC):

    def __init__(
        self, *, data_name: str = "clf_cat_albert", data_folder: str = None, **kwargs
    ):
        self.class_task = is_clf(data_name)

        super().__init__(data_name=data_name, data_folder=data_folder, **kwargs)

    @property
    def is_classification(self) -> bool:
        return self.class_task

    @property
    def scaler(self):
        return StandardScaler

    def download(self):
        return

    def preprocess(self, val_size, test_size):
        x, y = load_raw(self.name)
        self.split_save(x, y, val_size, test_size)
