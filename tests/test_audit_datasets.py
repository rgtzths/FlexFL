import inspect
import json
import math

import numpy as np
import pandas as pd
import pytest

import flexfl.builtins.DatasetABC as DatasetABC_module
import flexfl.datasets.Benchmark as Benchmark_module
from flexfl.datasets.Benchmark import Benchmark, is_clf


def _isolate(monkeypatch, tmp_path):
    metadata = tmp_path / "_metadata"
    metadata.mkdir()
    monkeypatch.setattr(DatasetABC_module, "METADATA_FOLDER", str(metadata))
    monkeypatch.setattr(DatasetABC_module, "DATA_FOLDER", str(tmp_path / "data"))


def _frame():
    n = 300
    rng = np.random.default_rng(0)
    y = np.arange(n, dtype=np.float64)
    x = np.column_stack([rng.normal(12000.0, 3000.0, n), y, np.full(n, 7.0)])
    x[[3, 50, 51, 120, 200, 299]] = -999.0
    return pd.DataFrame(x, columns=["a", "b", "c"]).assign(target=y)


def _fake_load(frame, calls):
    class _Hub:
        def to_pandas(self):
            return frame.copy()

    def load(*args, **kwargs):
        calls.append((args, kwargs))
        return {"train": _Hub()}

    return load


def test_audit_counts_all_sentinel_rows_and_preserves_isolated_999():
    import audit_datasets

    x = np.arange(90, dtype=np.float64).reshape(30, 3)
    x[1, 0] = 999.0
    y = np.arange(30) % 2
    for sentinel in (True, False):
        features = x.copy()
        if sentinel:
            features[[2, 21]] = -999.0
        data = {}
        for split, indices in (
            ("train", slice(0, 18)),
            ("val", slice(18, 24)),
            ("test", slice(24, 30)),
        ):
            data[f"x_{split}"] = features[indices]
            data[f"y_{split}"] = y[indices]
        row = audit_datasets.audit("clf_num_synthetic", data, set())
        assert row["n_all_sentinel_rows"] == (2 if sentinel else 0)
        assert row["n_sentinel_cells"] == (6 if sentinel else 0)
        assert ("all_sentinel_rows" in audit_datasets.flags(row)) is sentinel


@pytest.mark.parametrize("name", ("clf_num_synthetic", "reg_num_synthetic"))
def test_audit_rows_unchanged_by_refactor(name):
    import audit_datasets

    x = np.arange(90, dtype=np.float64).reshape(30, 3)
    x[1, 0] = 999.0
    x[[2, 21]] = -999.0
    y = np.arange(30) % 3 if is_clf(name) else np.arange(30) - 15.0
    data = {}
    for split, indices in (
        ("train", slice(0, 18)),
        ("val", slice(18, 24)),
        ("test", slice(24, 30)),
    ):
        data[f"x_{split}"] = x[indices]
        data[f"y_{split}"] = y[indices]
    expected = {
        "dataset": name,
        "tier20": name == "clf_num_synthetic",
        "task": "clf" if name == "clf_num_synthetic" else "reg",
        "n_train": 18,
        "n_val": 6,
        "n_test": 6,
        "n_feat": 3,
        "n_nonfinite": 0,
        "n_sentinel_cells": 6,
        "n_all_sentinel_rows": 2,
        "n_const": 0,
        "n_near_const": 0,
        "n_binary": 0,
        "n_sentinel_cand": 3,
        "sentinel_examples": (
            "f0=-999(5.6%,z=3.1);f1=-999(5.6%,z=4.1);f2=-999(5.6%,z=4.1)"
        ),
        "max_abs_z": 4.114949145779569,
        "worst_feat": 2,
        "n_feat_z_gt10": 0,
        "n_feat_z_gt50": 0,
        "frac_cells_z_gt10": 0.0,
        "n_continuous": 3,
        "max_excess_kurtosis": 17.831366080171758,
        "n_kurt_gt20": 0,
        "n_abs_skew_gt5": 0,
        "max_frac_outside_train_range": 0.9166666666666666,
        "frac_dup_rows_train": 0.0,
        "frac_dup_label_conflict": 0.0,
        "n_dup_cols": 0,
    }
    if name == "clf_num_synthetic":
        expected.update(
            max_abs_corr_feat_y=float("nan"),
            n_classes=3,
            min_class_frac=0.3333333333333333,
            imbalance_ratio=1.0,
        )
    else:
        expected.update(
            max_abs_corr_feat_y=0.3632157878531651,
            y_mean=-0.5,
            y_std=8.65544144839919,
            y_min=-15.0,
            y_max=14.0,
            y_median=-0.5,
            y_skew=0.0,
            y_excess_kurtosis=-1.2000000000000004,
            y_max_z=1.6752467319482305,
            y_top_value_frac=0.03333333333333333,
            y_log1p_skew=float("nan"),
        )
    row = audit_datasets.audit(name, data, {"clf_num_synthetic"})
    assert row.keys() == expected.keys()
    for key, value in expected.items():
        if isinstance(value, float):
            if math.isnan(value):
                assert math.isnan(row[key])
            else:
                assert row[key] == pytest.approx(value, rel=1e-12)
        else:
            assert type(row[key]) is type(value)
            assert row[key] == value


def test_load_splits_pins_revision_and_matches_production(monkeypatch, tmp_path):
    import audit_datasets

    _isolate(monkeypatch, tmp_path)
    calls = []
    fake = _fake_load(_frame(), calls)
    monkeypatch.setattr(Benchmark_module, "load_dataset", fake)
    assert (
        "keep_sentinel_rows" in inspect.signature(audit_datasets.load_splits).parameters
    )
    data = audit_datasets.load_splits(
        "reg_num_synthetic", "rev1", keep_sentinel_rows=False
    )
    assert calls == [
        (("inria-soda/tabular-benchmark", "reg_num_synthetic"), {"revision": "rev1"})
    ]
    assert list(data) == ["x_train", "y_train", "x_val", "y_val", "x_test", "y_test"]
    Benchmark(data_name="reg_num_synthetic").preprocess(0.2, 0.2)
    cache = tmp_path / "data" / "reg_num_synthetic" / "_data"
    for split in ("train", "val", "test"):
        np.testing.assert_array_equal(data[f"x_{split}"][:, 1], data[f"y_{split}"])
        np.testing.assert_array_equal(
            data[f"y_{split}"], np.load(cache / f"y_{split}.npy")
        )
    raw = audit_datasets.load_splits(
        "reg_num_synthetic", "rev1", keep_sentinel_rows=True
    )
    np.testing.assert_array_equal(
        np.sort(np.concatenate([raw[f"y_{s}"] for s in ("train", "val", "test")])),
        np.arange(300, dtype=np.float64),
    )
    assert calls[-1][1] == {"revision": "rev1"}


def test_load_splits_writes_no_metadata(monkeypatch, tmp_path):
    import audit_datasets

    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(Benchmark_module, "load_dataset", _fake_load(_frame(), []))
    audit_datasets.load_splits("reg_num_synthetic", "rev1", keep_sentinel_rows=True)
    assert list((tmp_path / "_metadata").iterdir()) == []


def test_audit_main_uses_provenance_revision(monkeypatch, tmp_path):
    import audit_datasets

    _isolate(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(Benchmark_module, "load_dataset", _fake_load(_frame(), calls))
    monkeypatch.setattr(audit_datasets, "provenance", lambda: {"hf_revision": "rev1"})
    names = tmp_path / "names.txt"
    names.write_text("reg_num_synthetic\n")
    tiers = tmp_path / "tier20.txt"
    tiers.write_text("reg_num_synthetic\n")
    out_json, out_csv = tmp_path / "audit.json", tmp_path / "audit.csv"
    audit_datasets.main(
        [
            "--names",
            str(names),
            "--tier20",
            str(tiers),
            "--out-json",
            str(out_json),
            "--out-csv",
            str(out_csv),
        ]
    )
    assert calls == [
        (("inria-soda/tabular-benchmark", "reg_num_synthetic"), {"revision": "rev1"})
    ]
    result = json.loads(out_json.read_text())
    assert result["provenance"]["hf_revision"] == "rev1"
    assert result["rows"][0]["n_all_sentinel_rows"] == 6
    assert result["rows"][0]["tier20"] is True
    assert "reg_num_synthetic" in out_csv.read_text()


def test_provenance_records_pinned_revision(monkeypatch):
    import audit_datasets
    from huggingface_hub import HfApi

    def check_output(command, **kwargs):
        assert command in (
            ["git", "rev-parse", "HEAD"],
            ["git", "status", "--porcelain"],
        )
        return "abc\n" if command[1] == "rev-parse" else ""

    def no_network(*args, **kwargs):
        raise AssertionError("provenance must not query the live Hub")

    monkeypatch.setattr(audit_datasets.subprocess, "check_output", check_output)
    monkeypatch.setattr(HfApi, "dataset_info", no_network)
    assert audit_datasets.provenance()["hf_revision"] == Benchmark_module.HF_REVISION


def test_provenance_hashes_every_audit_source(monkeypatch):
    import audit_datasets

    def check_output(command, **kwargs):
        assert command in (
            ["git", "rev-parse", "HEAD"],
            ["git", "status", "--porcelain"],
        )
        return "abc\n" if command[1] == "rev-parse" else ""

    monkeypatch.setattr(audit_datasets.subprocess, "check_output", check_output)
    assert set(audit_datasets.provenance()["sources_sha256"]) == {
        "scripts/audit_common.py",
        "scripts/audit_datasets.py",
        "scripts/audit_central_sanity.py",
        "scripts/render_dataset_audit.py",
        "src/flexfl/datasets/Benchmark.py",
        "src/flexfl/builtins/DatasetABC.py",
    }
