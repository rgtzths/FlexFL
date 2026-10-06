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


@pytest.mark.parametrize(
    "clf,scores,expected",
    [
        (
            True,
            [0.1, 0.5, 0.4, 0.3, 0.2, 0.9, 0.9, 0.9, 0.9, 0.9],
            {"best": 0.5, "best_epoch": 2, "epoch1": 0.1, "epochs": 5},
        ),
        (
            False,
            [0.5, 0.2, 0.3, 0.4, 0.6, 0.1, 0.1, 0.1, 0.1, 0.1],
            {"best": 0.2, "best_epoch": 2, "epoch1": 0.5, "epochs": 5},
        ),
    ],
    ids=["clf", "reg"],
)
def test_train_curve_tracks_best_and_stops_early(monkeypatch, clf, scores, expected):
    import audit_central_sanity

    monkeypatch.setattr(audit_central_sanity, "EPOCHS", 10)
    monkeypatch.setattr(audit_central_sanity, "PATIENCE", 3)
    iterator = iter(scores)
    monkeypatch.setattr(audit_central_sanity, "_score", lambda *args: next(iterator))
    calls = []

    class Model:
        def fit(self, *args, **kwargs):
            calls.append((args, kwargs))

        def predict(self, *args, **kwargs):
            return None

    x, y = np.zeros((2, 1)), np.zeros(2)
    result = audit_central_sanity._train_curve(Model(), x, y, x, y, clf, None)
    assert {key: result[key] for key in expected} == expected
    assert len(calls) == 5


def test_score_inverts_target_scaling():
    import audit_central_sanity

    assert (
        audit_central_sanity._score(
            True, np.array([0, 1]), np.array([[0.9, 0.1], [0.2, 0.8]]), None
        )
        == 1.0
    )
    assert (
        audit_central_sanity._score(
            False, np.array([10.0, 12.0]), np.array([[0.0], [1.0]]), (10.0, 2.0)
        )
        == 0.0
    )


def test_quantile_features_are_normal_and_monotone():
    import audit_central_sanity
    from scipy.stats import skew

    x = np.random.default_rng(0).exponential(size=(5000, 1))
    train, _ = audit_central_sanity._scale_features("quantile", x, x)
    assert abs(skew(train[:, 0])) < 0.1
    assert abs(train.mean()) < 0.05
    assert np.all(np.diff(train[np.argsort(x[:, 0]), 0]) >= 0)


@pytest.mark.parametrize("name", ("clf_num_synthetic", "reg_num_synthetic"))
def test_run_prepares_targets_and_caps_training_rows(monkeypatch, tmp_path, name):
    import audit_central_sanity

    monkeypatch.setitem(
        sys.modules,
        "keras",
        SimpleNamespace(
            utils=SimpleNamespace(set_random_seed=lambda seed: None),
            optimizers=SimpleNamespace(Adam=lambda learning_rate: learning_rate),
        ),
    )
    monkeypatch.setattr(audit_central_sanity, "MAX_TRAIN", 50)
    monkeypatch.setattr(audit_central_sanity, "EPOCHS", 1)
    rng = np.random.default_rng(0)
    clf = name.startswith("clf_")
    data = {
        "x_train": rng.normal(size=(80, 3)),
        "x_val": rng.normal(size=(20, 3)),
        "y_train": np.arange(80) % 2 if clf else 100 + 10 * rng.normal(size=80),
        "y_val": np.arange(20) % 3 if clf else 100 + 10 * rng.normal(size=20),
    }
    monkeypatch.setattr(audit_central_sanity, "load_splits", lambda *a, **kw: data)
    models = []

    class Model:
        def __init__(self, n_out):
            self.n_out = n_out
            self.fits = []

        def compile(self, **kwargs):
            pass

        def fit(self, x, y, **kwargs):
            self.fits.append((x.copy(), y.copy()))

        def predict(self, x, **kwargs):
            return np.zeros((len(x), self.n_out))

    def net(config, n_in, n_out, clf):
        model = Model(n_out)
        models.append(model)
        return model

    monkeypatch.setattr(audit_central_sanity, "_net", net)
    (tmp_path / f"{name}.json").write_text("{}")
    result = audit_central_sanity.run(name, "rev1", tmp_path)
    assert result["n_train_used"] == 50
    assert len(models) == len(audit_central_sanity.KINDS) * len(
        audit_central_sanity.LRS
    )
    for model in models:
        assert len(model.fits) == 1
        for x_fit, y_fit in model.fits:
            assert len(x_fit) == len(y_fit) == 50
            if clf:
                assert model.n_out == 3
            else:
                assert abs(y_fit.mean()) < 1e-9
                assert abs(y_fit.std() - 1.0) < 1e-9
