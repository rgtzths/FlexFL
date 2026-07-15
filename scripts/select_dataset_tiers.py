#!/usr/bin/env python3
"""Select diversity-maximizing, nested dataset tiers for a phased rollout (T10 budget).

Rather than ranking by size, this picks datasets to maximize coverage of the
meta-feature space first, then quantity: a farthest-point (maximin) ordering over
normalized dataset meta-features. Tier-10 ⊂ Tier-20 ⊂ all by construction, so
running tier 10, then 20, then all (the sweep is resumable — done configs skip)
progressively expands while keeping early coverage broad.

Meta-feature vector per dataset: is_classification, is_categorical (name prefix),
log10(n_samples), log10(n_features), log10(n_classes) — numeric dims min-max
normalized over the candidate set; binary dims already in [0, 1]. Deterministic.

Reads candidate dataset names from --candidates-file, else stdin (one per line),
else every dataset in the metadata dir. Prints the requested tier's names.
"""
import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_meta_features import DEFAULT_METADATA_DIR, extract  # noqa: E402


def feature_vector(name: str, mf: dict) -> list[float]:
    is_cat = 1.0 if "_cat_" in name else 0.0
    return [
        1.0 if mf["is_classification"] else 0.0,
        is_cat,
        math.log10(max(mf["n_samples"] or 1, 1)),
        math.log10(max(mf["n_features"] or 1, 1)),
        math.log10(max(mf["n_classes"] or 1, 1)),
    ]


def normalize(vectors: dict[str, list[float]]) -> dict[str, list[float]]:
    names = list(vectors)
    dims = len(next(iter(vectors.values())))
    lo = [min(vectors[n][d] for n in names) for d in range(dims)]
    hi = [max(vectors[n][d] for n in names) for d in range(dims)]
    out = {}
    for n in names:
        out[n] = [
            (vectors[n][d] - lo[d]) / (hi[d] - lo[d]) if hi[d] > lo[d] else 0.0
            for d in range(dims)
        ]
    return out


def dist(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def farthest_point_order(vectors: dict[str, list[float]]) -> list[str]:
    """Maximin ordering: seed with the point farthest from the centroid (ties by
    name for determinism), then repeatedly add the point maximizing the minimum
    distance to the already-selected set."""
    names = sorted(vectors)
    dims = len(next(iter(vectors.values())))
    centroid = [sum(vectors[n][d] for n in names) / len(names) for d in range(dims)]
    first = max(names, key=lambda n: (dist(vectors[n], centroid), n))

    order = [first]
    remaining = set(names) - {first}
    min_d = {n: dist(vectors[n], vectors[first]) for n in remaining}
    while remaining:
        nxt = max(remaining, key=lambda n: (min_d[n], n))
        order.append(nxt)
        remaining.discard(nxt)
        for n in remaining:
            d = dist(vectors[n], vectors[nxt])
            if d < min_d[n]:
                min_d[n] = d
    return order


def read_candidates(args) -> list[str] | None:
    if args.candidates_file:
        return [ln.strip() for ln in Path(args.candidates_file).read_text().splitlines() if ln.strip()]
    if not sys.stdin.isatty():
        data = sys.stdin.read()
        names = [ln.strip() for ln in data.splitlines() if ln.strip()]
        if names:
            return names
    return None


def main():
    p = argparse.ArgumentParser(description="Select diversity-maximizing nested dataset tiers.")
    p.add_argument("--tier", default="all", help="'10', '20', 'all', or any integer size")
    p.add_argument("--candidates-file", help="File of candidate dataset names (one per line)")
    p.add_argument("--metadata-dir", type=Path, default=DEFAULT_METADATA_DIR)
    p.add_argument("--tiers-out", help="Write the full nested-tier JSON here")
    args = p.parse_args()

    candidates = read_candidates(args)
    mf_all = extract(args.metadata_dir)
    if candidates is None:
        candidates = sorted(mf_all)

    missing = [c for c in candidates if c not in mf_all]
    if missing:
        raise SystemExit(f"No metadata for candidate dataset(s): {missing}")

    vectors = normalize({c: feature_vector(c, mf_all[c]) for c in candidates})
    order = farthest_point_order(vectors)

    if args.tiers_out:
        import json
        tiers = {"tier_10": order[:10], "tier_20": order[:20], "all": order}
        Path(args.tiers_out).write_text(json.dumps(tiers, indent=2))

    n = len(order) if args.tier == "all" else int(args.tier)
    for name in order[:n]:
        print(name)


if __name__ == "__main__":
    main()
