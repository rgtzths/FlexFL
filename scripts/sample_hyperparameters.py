#!/usr/bin/env python3
"""Deterministically sample FL hyperparameters for a single experiment run.

Prints the chosen values as flexfl CLI args on stdout (to append to the run
command) and, with --json-out, writes them as a JSON record for the meta-dataset
assembler. The draw is seeded from --key (the run identity), so a resumed or
retried run samples the SAME vector — the values are reproducible and stable
across the campaign.

Swept hyperparameters (decided in T07): learning_rate, batch_size, patience,
delta for every algorithm, plus local_epochs for the Decentralized algorithms
that do local training. The Centralized algorithms aggregate gradients per batch
and ignore local_epochs, so it is not swept for them.
"""
import argparse
import hashlib
import json
import math
import random

LOCAL_TRAINING_ALGOS = {"DecentralizedSync", "DecentralizedAsync"}


def seed_from_key(key: str) -> int:
    """Stable, cross-process seed (Python's hash() is salted; sha256 is not)."""
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")


def sample(algo: str, key: str) -> dict:
    rng = random.Random(seed_from_key(key))
    params = {
        "learning_rate": round(10 ** rng.uniform(-4, -2), 6),          # log-uniform [1e-4, 1e-2]
        "batch_size": rng.choice([256, 512, 1024, 2048]),
        "patience": rng.randint(3, 10),
        "delta": round(10 ** rng.uniform(math.log10(1e-3), math.log10(5e-2)), 5),  # log-uniform [1e-3, 5e-2]
    }
    if algo in LOCAL_TRAINING_ALGOS:
        params["local_epochs"] = rng.randint(1, 10)
    return params


def main():
    p = argparse.ArgumentParser(description="Sample FL hyperparameters for one run.")
    p.add_argument("--algo", required=True, help="FL algorithm name (decides local_epochs)")
    p.add_argument("--key", required=True, help="Stable run identity, e.g. 'combo|dataset|algo'")
    p.add_argument("--json-out", help="Optional path to write the sampled values as JSON")
    args = p.parse_args()

    params = sample(args.algo, args.key)

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(params, f, indent=2)

    print(" ".join(f"--{k} {v}" for k, v in params.items()))


if __name__ == "__main__":
    main()
