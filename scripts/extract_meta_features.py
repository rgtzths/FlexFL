#!/usr/bin/env python3
"""Extract per-dataset meta-features for the meta-learning table (T08, option B).

The architecture is held fixed (one Optuna config per dataset in
neural_nets/Benchmark.py), so raw architecture is collinear with dataset identity
and is NOT used as a predictor. Instead the meta-model predicts from dataset
meta-features that generalise across datasets. This reads them from
datasets/_metadata/<dataset>.json (the authoritative catalog written by
flexfl-preprocess) and emits them for the assembler (T11) to join per run.

Extracted: task (classification/regression), n_samples, n_features, n_classes,
is_classification. Class balance is NOT present in _metadata and is intentionally
left out here (computing it needs the raw labels) — see the task note.
"""
import argparse
import json
import math
from pathlib import Path

DEFAULT_METADATA_DIR = Path(__file__).resolve().parent.parent / "src/flexfl/datasets/_metadata"


def meta_features(meta: dict) -> dict:
    task = meta.get("type")
    input_shape = meta.get("input_shape") or []
    n_features = int(math.prod(input_shape)) if input_shape else None
    return {
        "task": task,
        "is_classification": task == "classification",
        "n_samples": meta.get("samples"),
        "n_features": n_features,
        "n_classes": meta.get("output_size"),
    }


def extract(metadata_dir: Path, data_name: str | None = None) -> dict:
    out = {}
    if data_name is not None:
        paths = [metadata_dir / f"{data_name}.json"]
    else:
        paths = sorted(metadata_dir.glob("*.json"))
    for p in paths:
        if not p.is_file():
            raise FileNotFoundError(f"Metadata file not found: {p}")
        with open(p) as f:
            meta = json.load(f)
        out[meta.get("name", p.stem)] = meta_features(meta)
    return out


def main():
    p = argparse.ArgumentParser(description="Extract dataset meta-features for the meta-dataset.")
    p.add_argument("--data_name", help="Single dataset; omit for all datasets in the metadata dir")
    p.add_argument("--metadata-dir", type=Path, default=DEFAULT_METADATA_DIR)
    p.add_argument("--out", help="Write JSON here; otherwise print to stdout")
    args = p.parse_args()

    result = extract(args.metadata_dir, args.data_name)
    text = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
