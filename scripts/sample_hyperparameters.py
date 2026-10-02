#!/usr/bin/env python3
"""Deterministically sample FL hyperparameters for a single experiment run.

Prints the chosen values as flexfl CLI args on stdout (to append to the run
command) and, with --json-out, writes them as a JSON record for the meta-dataset
assembler. The draw is seeded from --key (the run identity), so a resumed or
retried run samples the SAME vector — the values are reproducible and stable
across the campaign.

Swept hyperparameters (decided in T07): learning_rate and batch_size for every
algorithm, plus local_epochs for the Decentralized algorithms that do local
training. The Centralized algorithms aggregate gradients per batch and ignore
local_epochs, so it is not swept for them. Patience (PATIENCE) and delta (DELTA)
are fixed. Their former draws are still made and discarded so the swept values
for a key are unchanged.

CentralizedAsync on a classification dataset (data_name prefix clf_) maps the
same learning-rate draw onto log-uniform [3e-5, 1e-4] and multiplies it by
8 / n_workers, the combo's total worker count read from the key. At the shared
range its stale per-worker updates collapse classification models to a constant
prediction, and more workers make it worse. Regression keeps the shared range.

Every vector also carries the fixed global epoch cap, epochs = EPOCH_CAP, and the
fixed early-stop rule: early_stop_on = EARLY_STOP_ON (patience and delta apply to the
validation loss, with delta as a relative improvement) and min_epochs = MIN_EPOCHS
(no stop before that epoch).
"""

import argparse
import hashlib
import json
import math
import random

LOCAL_TRAINING_ALGOS = {"DecentralizedSync", "DecentralizedAsync"}
EPOCH_CAP = 200
EARLY_STOP_ON = "loss"
MIN_EPOCHS = 10
PATIENCE = 20
DELTA = 0.01
CA_CLASSIFICATION_LR = (3e-5, 1e-4)
CA_REFERENCE_WORKERS = 8


def seed_from_key(key: str) -> int:
    """Stable, cross-process seed (Python's hash() is salted; sha256 is not)."""
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")


def n_workers_from_combo(combo: str) -> int:
    """Total worker count of a combo named atnog-test1_<n1>_hobbit_<n2>_samwise_<n3>."""
    counts = combo.split("_")[1::2]
    if not counts or not all(c.isascii() and c.isdigit() for c in counts):
        raise ValueError(f"cannot read the worker count from combo {combo!r}")
    total = sum(int(c) for c in counts)
    if total <= 0:
        raise ValueError(f"cannot read the worker count from combo {combo!r}")
    return total


def centralized_async_classification_lr(exponent: float, combo: str) -> float:
    """Map the shared draw onto CA_CLASSIFICATION_LR, scaled by 8 / n_workers."""
    low, high = (math.log10(v) for v in CA_CLASSIFICATION_LR)
    learning_rate = 10 ** (low + (exponent + 4) / 2 * (high - low))
    scale = CA_REFERENCE_WORKERS / n_workers_from_combo(combo)
    return float(f"{learning_rate * scale:.3g}")


def sample(algo: str, key: str) -> dict:
    rng = random.Random(seed_from_key(key))
    exponent = rng.uniform(-4, -2)
    learning_rate = round(10**exponent, 6)  # log-uniform [1e-4, 1e-2]
    combo, data_name = (key.split("|") + ["", ""])[:2]
    if algo == "CentralizedAsync" and data_name.startswith("clf_"):
        learning_rate = centralized_async_classification_lr(exponent, combo)
    batch_size = rng.choice([256, 512, 1024, 2048])
    # Removing either discarded draw shifts local_epochs for every Decentralized key.
    rng.randint(3, 10)
    rng.uniform(math.log10(1e-3), math.log10(5e-2))
    params = {
        "learning_rate": learning_rate,
        "batch_size": batch_size,
        "patience": PATIENCE,
        "delta": DELTA,
    }
    if algo in LOCAL_TRAINING_ALGOS:
        params["local_epochs"] = rng.randint(1, 10)
    params["epochs"] = EPOCH_CAP
    params["early_stop_on"] = EARLY_STOP_ON
    params["min_epochs"] = MIN_EPOCHS
    return params


def main():
    p = argparse.ArgumentParser(description="Sample FL hyperparameters for one run.")
    p.add_argument(
        "--algo", required=True, help="FL algorithm name (decides local_epochs)"
    )
    p.add_argument(
        "--key",
        required=True,
        help="Stable run identity, e.g. 'combo|dataset|algo|seed'",
    )
    p.add_argument(
        "--json-out", help="Optional path to write the sampled values as JSON"
    )
    args = p.parse_args()

    params = sample(args.algo, args.key)

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(params, f, indent=2)

    print(" ".join(f"--{k} {v}" for k, v in params.items()))


if __name__ == "__main__":
    main()
