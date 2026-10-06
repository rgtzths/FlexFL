"""Helpers and constants shared by the dataset audit scripts."""

import hashlib
from pathlib import Path

LRS = (1e-3, 1e-4)
KINDS = ("standard", "clip", "quantile")


def score_key(kind, lr):
    return f"{kind}_lr{lr:g}"


HEADLINE_KEY = score_key("standard", LRS[0])


def read_lines(path):
    return [
        line.strip() for line in Path(path).read_text().splitlines() if line.strip()
    ]


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def better(clf, value, reference):
    return value > reference if clf else value < reference
