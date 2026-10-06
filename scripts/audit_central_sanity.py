#!/usr/bin/env python3
"""Train each dataset's HPO network for central preprocessing sanity checks.

Reads dataset names and HPO configs, compares standard, clip and quantile
features against a constant baseline and a boosting reference, and writes
JSONL plus a provenance sidecar. Requires the ml extra. Run from the repo root:

    .venv/bin/python scripts/audit_central_sanity.py --names names.txt \
        --hpo-dir results/hyperparameter_optimization --out sanity.jsonl
"""

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
from audit_common import KINDS, LRS, better, read_lines, score_key, sha256_file
from audit_datasets import load_splits, provenance
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)
from sklearn.metrics import matthews_corrcoef
from sklearn.preprocessing import QuantileTransformer, StandardScaler

from flexfl.datasets.Benchmark import is_clf

MAX_TRAIN = 100_000
EPOCHS = 40
PATIENCE = 8
BATCH = 512
SEED = 42


def _smape(y, p):
    y, p = np.ravel(y), np.ravel(p)
    d = (np.abs(y) + np.abs(p)) / 2
    return float(np.mean(np.where(d == 0, 0, np.abs(y - p) / np.where(d == 0, 1, d))))


def _scale_features(kind, xtr, xva):
    if kind == "quantile":
        transformer = QuantileTransformer(
            output_distribution="normal",
            n_quantiles=min(1000, len(xtr)),
            subsample=100_000,
            random_state=0,
        )
        return transformer.fit_transform(xtr), transformer.transform(xva)
    scaler = StandardScaler()
    x_train_scaled, x_val_scaled = scaler.fit_transform(xtr), scaler.transform(xva)
    if kind == "clip":
        return np.clip(x_train_scaled, -5, 5), np.clip(x_val_scaled, -5, 5)
    return x_train_scaled, x_val_scaled


def _net(config, n_in, n_out, clf):
    import keras

    layers = [keras.layers.Input(shape=(n_in,))]
    for i in range(config["n_layers"]):
        layers.append(
            keras.layers.Dense(
                config[f"n_units_l{i}"],
                activation="relu",
                kernel_regularizer=keras.regularizers.L2(config["weight_decay"]),
            )
        )
    layers.append(keras.layers.Dense(n_out))
    if clf:
        layers.append(keras.layers.Softmax())
    return keras.models.Sequential(layers)


def _score(clf, y, pred, target):
    if clf:
        return float(matthews_corrcoef(y, np.argmax(pred, axis=1)))
    mean, std = target
    return _smape(y, np.ravel(pred) * std + mean)


def _train_curve(model, x_train, y_fit, x_val, y_val, clf, target):
    best, best_epoch, first, wait, t0 = None, 0, None, 0, time.time()
    for epoch in range(1, EPOCHS + 1):
        model.fit(x_train, y_fit, batch_size=BATCH, epochs=1, verbose=0, shuffle=True)
        val_score = _score(
            clf, y_val, model.predict(x_val, batch_size=4096, verbose=0), target
        )
        first = val_score if first is None else first
        if best is None or better(clf, val_score, best):
            best, best_epoch, wait = val_score, epoch, 0
        else:
            wait += 1
            if wait >= PATIENCE:
                break
    return {
        "best": best,
        "best_epoch": best_epoch,
        "epoch1": first,
        "epochs": epoch,
        "secs": round(time.time() - t0, 1),
    }


def _reference_scores(clf, xtr, ytr, xva, yva):
    if clf:
        ytr, yva = ytr.astype(int), yva.astype(int)
        ref = HistGradientBoostingClassifier(random_state=SEED).fit(xtr, ytr)
        return {
            "y_val": yva,
            "y_fit": ytr,
            "n_out": int(max(ytr.max(), yva.max()) + 1),
            "loss": "sparse_categorical_crossentropy",
            "target": None,
            "constant": 0.0,
            "hgb": float(matthews_corrcoef(yva, ref.predict(xva))),
        }
    ytr, yva = ytr.astype(np.float64), yva.astype(np.float64)
    mean, std = ytr.mean(), ytr.std() or 1.0
    ref = HistGradientBoostingRegressor(random_state=SEED).fit(xtr, ytr)
    return {
        "y_val": yva,
        "y_fit": (ytr - mean) / std,
        "n_out": 1,
        "loss": "mse",
        "target": (mean, std),
        "constant": _smape(yva, np.full_like(yva, mean)),
        "hgb": _smape(yva, ref.predict(xva)),
    }


def run(name, revision, hpo_dir, keep_sentinel_rows=False):
    import keras

    data = load_splits(name, revision, keep_sentinel_rows=keep_sentinel_rows)
    xtr, ytr, xva, yva = (data[k] for k in ("x_train", "y_train", "x_val", "y_val"))
    clf = is_clf(name)
    rng = np.random.default_rng(SEED)
    if len(xtr) > MAX_TRAIN:
        idx = rng.choice(len(xtr), MAX_TRAIN, replace=False)
        xtr, ytr = xtr[idx], ytr[idx]
    config = json.loads((Path(hpo_dir) / f"{name}.json").read_text())
    out = {
        "dataset": name,
        "n_train_used": len(xtr),
        "keep_sentinel_rows": keep_sentinel_rows,
    }
    setup = _reference_scores(clf, xtr, ytr, xva, yva)
    out["constant"], out["hgb"] = setup["constant"], setup["hgb"]
    for kind in KINDS:
        x_train_scaled, x_val_scaled = _scale_features(kind, xtr, xva)
        for lr in LRS:
            keras.utils.set_random_seed(SEED)
            model = _net(config, x_train_scaled.shape[1], setup["n_out"], clf)
            model.compile(
                optimizer=keras.optimizers.Adam(learning_rate=lr), loss=setup["loss"]
            )
            out[score_key(kind, lr)] = _train_curve(
                model,
                x_train_scaled,
                setup["y_fit"],
                x_val_scaled,
                setup["y_val"],
                clf,
                setup["target"],
            )
    return out


def build_provenance(names, hpo_dir, keep_sentinel_rows):
    prov = provenance()
    prov["run_constants"] = {
        "MAX_TRAIN": MAX_TRAIN,
        "EPOCHS": EPOCHS,
        "PATIENCE": PATIENCE,
        "BATCH": BATCH,
        "LRS": LRS,
        "SEED": SEED,
    }
    prov["keep_sentinel_rows"] = keep_sentinel_rows
    prov["hpo_sha256"] = {name: sha256_file(hpo_dir / f"{name}.json") for name in names}
    return prov


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--names", type=Path, required=True)
    parser.add_argument("--hpo-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--keep-sentinel-rows", action="store_true")
    args = parser.parse_args(argv)
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    import keras

    names = read_lines(args.names)
    prov = build_provenance(names, args.hpo_dir, args.keep_sentinel_rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("")
    Path(f"{args.out}.provenance.json").write_text(json.dumps(prov, indent=2))
    keras.utils.set_random_seed(SEED)
    for name in names:
        t0 = time.time()
        r = run(name, prov["hf_revision"], args.hpo_dir, args.keep_sentinel_rows)
        r["secs_total"] = round(time.time() - t0, 1)
        with args.out.open("a") as fh:
            fh.write(json.dumps(r) + "\n")
        print(name, r["secs_total"], flush=True)


if __name__ == "__main__":
    main()
