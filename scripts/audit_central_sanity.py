import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
from audit_datasets import load_splits, provenance
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)
from sklearn.metrics import matthews_corrcoef
from sklearn.preprocessing import QuantileTransformer, StandardScaler

MAX_TRAIN = 100_000
EPOCHS = 40
PATIENCE = 8
BATCH = 512
LRS = (1e-3, 1e-4)
SEED = 42


def smape(y, p):
    y, p = np.ravel(y), np.ravel(p)
    d = (np.abs(y) + np.abs(p)) / 2
    return float(np.mean(np.where(d == 0, 0, np.abs(y - p) / np.where(d == 0, 1, d))))


def features(kind, xtr, xva):
    if kind == "quantile":
        q = QuantileTransformer(
            output_distribution="normal",
            n_quantiles=min(1000, len(xtr)),
            subsample=100_000,
            random_state=0,
        )
        return q.fit_transform(xtr), q.transform(xva)
    s = StandardScaler()
    a, b = s.fit_transform(xtr), s.transform(xva)
    if kind == "clip":
        a, b = np.clip(a, -5, 5), np.clip(b, -5, 5)
    return a, b


def net(cfg, n_in, n_out, clf):
    import keras

    layers = [keras.layers.Input(shape=(n_in,))]
    for i in range(cfg["n_layers"]):
        layers.append(
            keras.layers.Dense(
                cfg[f"n_units_l{i}"],
                activation="relu",
                kernel_regularizer=keras.regularizers.L2(cfg["weight_decay"]),
            )
        )
    layers.append(keras.layers.Dense(n_out))
    if clf:
        layers.append(keras.layers.Softmax())
    return keras.models.Sequential(layers)


def score(clf, y, pred, target):
    if clf:
        return float(matthews_corrcoef(y, np.argmax(pred, axis=1)))
    return smape(y, np.ravel(pred) * target[1] + target[0])


def run(name, revision, hpo_dir, keep_sentinel_rows=False):
    import keras

    data = load_splits(name, revision, drop_sentinel=not keep_sentinel_rows)
    xtr, ytr, xva, yva = (data[k] for k in ("x_train", "y_train", "x_val", "y_val"))
    clf = name.startswith("clf_")
    rng = np.random.default_rng(SEED)
    if len(xtr) > MAX_TRAIN:
        idx = rng.choice(len(xtr), MAX_TRAIN, replace=False)
        xtr, ytr = xtr[idx], ytr[idx]
    cfg = json.loads((Path(hpo_dir) / f"{name}.json").read_text())
    out = {
        "dataset": name,
        "n_train_used": len(xtr),
        "keep_sentinel_rows": keep_sentinel_rows,
    }
    if clf:
        ytr, yva = ytr.astype(int), yva.astype(int)
        n_out, loss, target = (
            int(max(ytr.max(), yva.max()) + 1),
            "sparse_categorical_crossentropy",
            None,
        )
        out["constant"] = 0.0
        ref = HistGradientBoostingClassifier(random_state=SEED).fit(xtr, ytr)
        out["hgb"] = float(matthews_corrcoef(yva, ref.predict(xva)))
        ytr_fit = ytr
    else:
        ytr, yva = ytr.astype(np.float64), yva.astype(np.float64)
        target = (ytr.mean(), ytr.std() or 1.0)
        n_out, loss = 1, "mse"
        out["constant"] = smape(yva, np.full_like(yva, target[0]))
        ref = HistGradientBoostingRegressor(random_state=SEED).fit(xtr, ytr)
        out["hgb"] = smape(yva, ref.predict(xva))
        ytr_fit = (ytr - target[0]) / target[1]
    for kind in ("standard", "clip", "quantile"):
        a, b = features(kind, xtr, xva)
        for lr in LRS:
            keras.utils.set_random_seed(SEED)
            m = net(cfg, a.shape[1], n_out, clf)
            m.compile(optimizer=keras.optimizers.Adam(learning_rate=lr), loss=loss)
            best, best_ep, first, wait, t0 = None, 0, None, 0, time.time()
            for ep in range(1, EPOCHS + 1):
                m.fit(a, ytr_fit, batch_size=BATCH, epochs=1, verbose=0, shuffle=True)
                s = score(clf, yva, m.predict(b, batch_size=4096, verbose=0), target)
                first = s if first is None else first
                better = best is None or (s > best if clf else s < best)
                if better:
                    best, best_ep, wait = s, ep, 0
                else:
                    wait += 1
                    if wait >= PATIENCE:
                        break
            out[f"{kind}_lr{lr:g}"] = {
                "best": best,
                "best_epoch": best_ep,
                "epoch1": first,
                "epochs": ep,
                "secs": round(time.time() - t0, 1),
            }
    return out


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--names", type=Path, required=True)
    parser.add_argument("--hpo-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--keep-sentinel-rows", action="store_true")
    args = parser.parse_args(argv)
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    import keras

    names = [
        line.strip() for line in args.names.read_text().splitlines() if line.strip()
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("")
    prov = provenance()
    prov["run_constants"] = {
        "MAX_TRAIN": MAX_TRAIN,
        "EPOCHS": EPOCHS,
        "PATIENCE": PATIENCE,
        "BATCH": BATCH,
        "LRS": LRS,
        "SEED": SEED,
    }
    prov["keep_sentinel_rows"] = args.keep_sentinel_rows
    prov["hpo_sha256"] = {
        name: hashlib.sha256((args.hpo_dir / f"{name}.json").read_bytes()).hexdigest()
        for name in names
    }
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
