import numpy as np
import pandas as pd
import pytest

from flexfl.builtins.DatasetABC import DatasetABC


def _mixed_frame():
    # a numeric feature block with a string label column, as several
    # tabular-benchmark classification sets ship
    return pd.DataFrame({
        "f0": [0.429715, 0.5, 0.61],
        "f1": [2, 3, 4],
        "f2": [0.106383, 0.2, 0.3],
        "label": ["UP", "DOWN", "UP"],
    })


def test_dataframe_values_is_object_for_a_mixed_frame():
    df = _mixed_frame()
    assert df.values.dtype == object


def test_dropping_the_label_column_first_yields_numeric_features():
    df = _mixed_frame()
    x = df.iloc[:, :-1].to_numpy(dtype=np.float64)
    assert x.dtype == np.float64
    assert x.shape == (3, 3)


class _Dataset(DatasetABC):
    def __init__(self, path):
        self.data_path = str(path)
        self.metadata = {}
        self.output_size = 1

    @property
    def is_classification(self):
        return True

    @property
    def scaler(self):
        return None

    def download(self):
        return

    def preprocess(self, val_size, test_size):
        return


def test_save_data_rejects_object_dtype_features(tmp_path):
    ds = _Dataset(tmp_path)
    x = np.array([[0.4, 2], [0.5, 3]], dtype=object)
    y = np.array([0, 1])

    with pytest.raises(ValueError, match="dtype=object"):
        ds.save_data(x, y, "train")

    assert not (tmp_path / "x_train.npy").exists()


def test_save_data_rejects_object_dtype_labels(tmp_path):
    ds = _Dataset(tmp_path)
    x = np.array([[0.4, 2.0], [0.5, 3.0]])
    y = np.array(["UP", "DOWN"], dtype=object)

    with pytest.raises(ValueError, match="dtype=object"):
        ds.save_data(x, y, "train")


def test_save_data_accepts_numeric_arrays(tmp_path):
    ds = _Dataset(tmp_path)
    x = np.array([[0.4, 2.0], [0.5, 3.0]])
    y = np.array([0, 1])

    ds.save_data(x, y, "train")

    assert np.load(tmp_path / "x_train.npy").dtype == np.float64
    assert np.load(tmp_path / "y_train.npy").dtype.kind in "iu"
