import json

import numpy as np
import pandas as pd

import flexfl.builtins.DatasetABC as DatasetABC_module
import flexfl.datasets.Benchmark as Benchmark_module
from flexfl.datasets.Benchmark import Benchmark


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


def test_load_splits_pins_revision_and_matches_production(monkeypatch, tmp_path):
    import audit_datasets

    _isolate(monkeypatch, tmp_path)
    calls = []
    fake = _fake_load(_frame(), calls)
    monkeypatch.setattr(audit_datasets, "load_dataset", fake)
    monkeypatch.setattr(Benchmark_module, "load_dataset", fake)
    data = audit_datasets.load_splits("reg_num_synthetic", "rev1", drop_sentinel=True)
    assert calls == [
        (("inria-soda/tabular-benchmark", "reg_num_synthetic"), {"revision": "rev1"})
    ]
    Benchmark(data_name="reg_num_synthetic").preprocess(0.2, 0.2)
    cache = tmp_path / "data" / "reg_num_synthetic" / "_data"
    for split in ("train", "val", "test"):
        np.testing.assert_array_equal(
            data[f"y_{split}"], np.load(cache / f"y_{split}.npy")
        )
    raw = audit_datasets.load_splits("reg_num_synthetic", "rev1", drop_sentinel=False)
    np.testing.assert_array_equal(
        np.sort(np.concatenate([raw[f"y_{s}"] for s in ("train", "val", "test")])),
        np.arange(300, dtype=np.float64),
    )
    assert calls[-1][1] == {"revision": "rev1"}


def test_audit_main_uses_provenance_revision(monkeypatch, tmp_path):
    import audit_datasets

    _isolate(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(audit_datasets, "load_dataset", _fake_load(_frame(), calls))
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


def test_audit_central_sanity_imports_without_tensorflow():
    import audit_central_sanity

    assert audit_central_sanity.LRS == (1e-3, 1e-4)
    assert audit_central_sanity.SEED == 42
