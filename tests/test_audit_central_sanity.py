import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


def test_audit_central_sanity_imports_without_keras(monkeypatch):
    monkeypatch.setitem(sys.modules, "keras", None)
    monkeypatch.setitem(sys.modules, "tensorflow", None)
    monkeypatch.delitem(sys.modules, "audit_central_sanity", raising=False)
    module = importlib.import_module("audit_central_sanity")
    assert module.LRS == (1e-3, 1e-4)
    assert module.SEED == 42


def test_smape_and_scale_features():
    import audit_central_sanity

    assert audit_central_sanity._smape([1, 2], [1, 2]) == 0.0
    assert audit_central_sanity._smape([0], [0]) == 0.0
    assert audit_central_sanity._smape([2], [1]) == pytest.approx(2 / 3)
    x = np.tile([-1.0, 1.0], 10000).reshape(-1, 1)
    x[-1] = 100.0
    train, val = audit_central_sanity._scale_features("clip", x, x)
    assert train.min() >= -5.0
    assert train.max() <= 5.0
    assert val.min() >= -5.0
    assert val.max() <= 5.0
    train, val = audit_central_sanity._scale_features("standard", x, x)
    np.testing.assert_allclose(train.mean(axis=0), 0.0, atol=1e-12)
    np.testing.assert_allclose(train.std(axis=0), 1.0)
    np.testing.assert_array_equal(train, val)


@pytest.mark.parametrize("keep_sentinel_rows", (True, False))
def test_run_forwards_keep_sentinel_rows(monkeypatch, tmp_path, keep_sentinel_rows):
    import audit_central_sanity

    class _Stop(Exception):
        pass

    calls = []

    def load_splits(name, revision, **kwargs):
        calls.append((name, revision, kwargs))
        raise _Stop

    monkeypatch.setitem(sys.modules, "keras", SimpleNamespace())
    monkeypatch.setattr(audit_central_sanity, "load_splits", load_splits)
    with pytest.raises(_Stop):
        audit_central_sanity.run(
            "clf_num_synthetic", "rev1", tmp_path, keep_sentinel_rows=keep_sentinel_rows
        )
    assert calls == [
        ("clf_num_synthetic", "rev1", {"keep_sentinel_rows": keep_sentinel_rows})
    ]
    assert calls[0][2]["keep_sentinel_rows"] is keep_sentinel_rows


def test_main_sidecars_satisfy_renderer(monkeypatch, tmp_path):
    import audit_central_sanity
    import render_dataset_audit

    monkeypatch.setitem(
        sys.modules,
        "keras",
        SimpleNamespace(utils=SimpleNamespace(set_random_seed=lambda seed: None)),
    )
    monkeypatch.setattr(
        audit_central_sanity,
        "provenance",
        lambda: {"hf_revision": "rev1", "sources_sha256": {"a": "b"}},
    )

    def run(name, revision, hpo_dir, keep_sentinel_rows=False):
        return {
            "dataset": name,
            "keep_sentinel_rows": keep_sentinel_rows,
            "constant": 0.0,
            "hgb": 0.5,
            **{key: {"best": 0.6} for _, key in render_dataset_audit.SANITY_COLUMNS},
        }

    monkeypatch.setattr(audit_central_sanity, "run", run)
    hpo_dir = tmp_path / "hpo"
    hpo_dir.mkdir()
    (hpo_dir / "clf_num_MiniBooNE.json").write_text("{}")
    names = tmp_path / "names.txt"
    names.write_text("clf_num_MiniBooNE\n")
    results = []
    for filename, keep in (("after.jsonl", False), ("before.jsonl", True)):
        output = tmp_path / filename
        args = ["--names", str(names), "--hpo-dir", str(hpo_dir), "--out", str(output)]
        audit_central_sanity.main(args + (["--keep-sentinel-rows"] if keep else []))
        results.extend(
            (
                [json.loads(line) for line in output.read_text().splitlines()],
                json.loads(Path(f"{output}.provenance.json").read_text()),
            )
        )
    after, after_prov, before, before_prov = results
    render_dataset_audit._validate(
        {"provenance": {"hf_revision": "rev1", "sources_sha256": {"a": "b"}}},
        after,
        after_prov,
        before,
        before_prov,
    )
    assert after_prov["run_constants"]["LRS"] == [0.001, 0.0001]
