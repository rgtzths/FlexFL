import numpy as np
import pandas as pd
import pytest
from sklearn.preprocessing import StandardScaler

import flexfl.builtins.DatasetABC as DatasetABC_module
from flexfl.datasets.IOT_DNL import IOT_DNL
from flexfl.datasets.TON_IOT import TON_IOT
from flexfl.datasets.UNSW import UNSW
from flexfl.datasets.Slicing5g import Slicing5g


def _build_dataset(monkeypatch, tmp_path, cls):
    metadata_dir = tmp_path / "_metadata"
    metadata_dir.mkdir()
    monkeypatch.setattr(DatasetABC_module, "DATA_FOLDER", str(tmp_path / "data"))
    monkeypatch.setattr(DatasetABC_module, "METADATA_FOLDER", str(metadata_dir))
    return cls()


def _iot_dnl_frame():
    n = 10
    df = pd.DataFrame({
        "normality": [0, 1, 0, 1, 0, 1, 0, 1, 0, 1],
        "frame.number": list(range(n)),
        "frame.time": [f"t{i}" for i in range(n)],
        "f1": [float(i) for i in range(n)],
        "f2": [float(i) * 2 for i in range(n)],
    })
    df.loc[2, "normality"] = np.nan
    df.loc[7, "f1"] = np.nan
    return df


def _ton_iot_frame():
    n = 10
    df = pd.DataFrame({
        "Label": [0, 1, 0, 1, 0, 1, 0, 1, 0, 1],
        "L4_SRC_PORT": list(range(n)),
        "L4_DST_PORT": list(range(n)),
        "Attack": ["x"] * n,
        "f1": [float(i) for i in range(n)],
        "f2": [float(i) * 2 for i in range(n)],
    })
    df.loc[2, "Label"] = np.nan
    df.loc[7, "f1"] = np.nan
    return df


def _unsw_frame():
    n = 10
    df = pd.DataFrame({
        "Label": [0, 1, 0, 1, 0, 1, 0, 1, 0, 1],
        "IPV4_SRC_ADDR": ["1.1.1.1"] * n,
        "L4_SRC_PORT": list(range(n)),
        "IPV4_DST_ADDR": ["2.2.2.2"] * n,
        "L4_DST_PORT": list(range(n)),
        "Attack": ["x"] * n,
        "f1": [float(i) for i in range(n)],
        "f2": [float(i) * 2 for i in range(n)],
    })
    df.loc[2, "Label"] = np.nan
    df.loc[7, "f1"] = np.nan
    return df


def _slicing5g_frame():
    n = 10
    df = pd.DataFrame({
        "Unnamed: 0": list(range(n)),
        "Use CaseType (Input 1)": ["a", "b"] * (n // 2),
        "LTE/5G UE Category (Input 2)": list(range(n)),
        "Technology Supported (Input 3)": ["x", "y"] * (n // 2),
        "Day (Input4)": ["mon", "tue"] * (n // 2),
        "QCI (Input 6)": [1, 2] * (n // 2),
        "Packet Loss Rate (Reliability)": [0.1, 0.2] * (n // 2),
        "Packet Delay Budget (Latency)": [10, 20] * (n // 2),
        "Raw Numeric Feature": [float(i) for i in range(n)],
        "Slice Type (Output)": [0, 1, 2, 0, 1, 2, 0, 1, 2, 0],
    })
    # NaN in a non-encoded numeric feature: it survives to x_*.npy unless dropna runs.
    df.loc[2, "Raw Numeric Feature"] = np.nan
    df.loc[7, "Raw Numeric Feature"] = np.nan
    return df


def _assert_no_nan_and_row_count(ds, expected_rows):
    x_train, y_train = ds.load_data("train")
    x_val, y_val = ds.load_data("val")
    x_test, y_test = ds.load_data("test")
    total_rows = x_train.shape[0] + x_val.shape[0] + x_test.shape[0]
    assert total_rows == expected_rows
    for arr in (x_train, x_val, x_test, y_train, y_val, y_test):
        assert not np.isnan(arr.astype(float)).any()


def test_iot_dnl_dropna_reassigned(monkeypatch, tmp_path):
    df = _iot_dnl_frame()
    monkeypatch.setattr(pd, "read_csv", lambda *a, **kw: df.copy())
    ds = _build_dataset(monkeypatch, tmp_path, IOT_DNL)
    ds.preprocess(val_size=0.2, test_size=0.2)
    _assert_no_nan_and_row_count(ds, 8)


def test_ton_iot_dropna_reassigned(monkeypatch, tmp_path):
    df = _ton_iot_frame()
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **kw: df.copy())
    ds = _build_dataset(monkeypatch, tmp_path, TON_IOT)
    ds.preprocess(val_size=0.2, test_size=0.2)
    _assert_no_nan_and_row_count(ds, 8)


def test_unsw_dropna_reassigned(monkeypatch, tmp_path):
    df = _unsw_frame()
    monkeypatch.setattr(pd, "read_csv", lambda *a, **kw: df.copy())
    ds = _build_dataset(monkeypatch, tmp_path, UNSW)
    ds.preprocess(val_size=0.2, test_size=0.2)
    _assert_no_nan_and_row_count(ds, 8)


def test_slicing5g_dropna_reassigned(monkeypatch, tmp_path):
    df = _slicing5g_frame()
    monkeypatch.setattr(pd, "read_excel", lambda *a, **kw: df.copy())
    ds = _build_dataset(monkeypatch, tmp_path, Slicing5g)
    ds.preprocess(val_size=0.2, test_size=0.2)
    _assert_no_nan_and_row_count(ds, 8)


def test_ton_iot_scaler_is_standard_scaler():
    assert TON_IOT.scaler.fget(object.__new__(TON_IOT)) is StandardScaler


def test_slicing5g_download_raises_without_env_var(monkeypatch):
    monkeypatch.delenv("SLICING5G_URL", raising=False)
    with pytest.raises(ValueError):
        Slicing5g.download(object.__new__(Slicing5g))
