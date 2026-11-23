#!/usr/bin/env python3
"""Noise-floor rerun list: stratified sampler and replay helpers."""

import argparse
import csv
import json
import math
import os
import random
import sys
import tempfile
from pathlib import Path

from sample_hyperparameters import sample

REPEAT1_SEED = 42
STRATEGIES = ("iid", "non_iid", "dirichlet")
LIST_FIELDS = (
    "strategy",
    "n1",
    "n2",
    "n3",
    "data_name",
    "fl_algo",
    "seed",
    "expected_hyperparameters",
    "expected_division",
)
EXPECTED_FIELDS = ("expected_hyperparameters", "expected_division")
STR_FIELDS = ("strategy", "data_name", "fl_algo")
INT_FIELDS = ("n1", "n2", "n3", "seed")
DEFAULT_BANDS = "6,17,33,45,57"
CSV_COLUMNS = (
    "strategy",
    "combo",
    "n_atnog_test1",
    "n_hobbit",
    "n_samwise",
    "num_workers",
    "dataset",
    "fl_algo",
    "repeat",
    "total_time_s",
)
OTHER_BAND = "other"


def read_list(path: Path, allow_missing_expected: bool = False) -> list[dict]:
    entries = []
    with open(path, "r") as f:
        for lineno, raw in enumerate(f, 1):
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}: line {lineno}: invalid JSON ({exc.msg})")
            if not isinstance(entry, dict):
                raise ValueError(f"{path}: line {lineno}: not a JSON object")
            for field in LIST_FIELDS:
                if field in entry:
                    continue
                if allow_missing_expected and field in EXPECTED_FIELDS:
                    continue
                raise ValueError(f"{path}: line {lineno}: missing field {field!r}")
            for field in STR_FIELDS:
                if not isinstance(entry[field], str):
                    raise ValueError(
                        f"{path}: line {lineno}: {field!r} must be a string"
                    )
            for field in INT_FIELDS:
                value = entry[field]
                if not isinstance(value, int) or isinstance(value, bool):
                    raise ValueError(
                        f"{path}: line {lineno}: {field!r} must be an integer"
                    )
            for field in EXPECTED_FIELDS:
                if field in entry and not isinstance(entry[field], dict):
                    raise ValueError(
                        f"{path}: line {lineno}: {field!r} must be an object"
                    )
            entries.append(entry)
    return entries


def combo_of(entry: dict) -> str:
    return f"atnog-test1_{entry['n1']}_hobbit_{entry['n2']}_samwise_{entry['n3']}"


def key_of(entry: dict) -> str:
    return f"{combo_of(entry)}|{entry['data_name']}|{entry['fl_algo']}|{entry['seed']}"


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def diff_json(
    expected: object, actual: object, rel_tol: float = 1e-9, _path: str = "$"
) -> list[str]:
    if isinstance(expected, dict) and isinstance(actual, dict):
        out = []
        for key in expected:
            if key not in actual:
                out.append(f"{_path}.{key}: missing key in actual")
            else:
                out.extend(
                    diff_json(expected[key], actual[key], rel_tol, f"{_path}.{key}")
                )
        for key in actual:
            if key not in expected:
                out.append(f"{_path}.{key}: unexpected key in actual")
        return out
    if isinstance(expected, list) and isinstance(actual, list):
        out = []
        if len(expected) != len(actual):
            out.append(
                f"{_path}: expected {len(expected)} items, actual {len(actual)} items"
            )
        for i, (e, a) in enumerate(zip(expected, actual)):
            out.extend(diff_json(e, a, rel_tol, f"{_path}[{i}]"))
        return out
    if _is_number(expected) and _is_number(actual):
        if expected == actual or math.isclose(expected, actual, rel_tol=rel_tol):
            return []
        if math.isnan(expected) and math.isnan(actual):
            return []
    elif type(expected) is type(actual) and expected == actual:
        return []
    return [f"{_path}: expected {expected!r}, actual {actual!r}"]


def validate_entries(entries: list[dict]) -> None:
    if not entries:
        raise ValueError("list is empty")
    problems = []
    seen = set()
    for i, entry in enumerate(entries, 1):
        who = f"entry {i} ({key_of(entry)})"
        if entry["seed"] != REPEAT1_SEED:
            problems.append(f"{who}: seed {entry['seed']} is not {REPEAT1_SEED}")
        if entry["strategy"] not in STRATEGIES:
            problems.append(
                f"{who}: strategy {entry['strategy']!r} is not one of {STRATEGIES}"
            )
        for field in ("n1", "n2", "n3"):
            if entry[field] <= 0:
                problems.append(f"{who}: {field} must be positive, got {entry[field]}")
        ident = tuple(
            entry[f] for f in ("strategy", "n1", "n2", "n3", "data_name", "fl_algo")
        )
        if ident in seen:
            problems.append(f"{who}: duplicate configuration")
        seen.add(ident)
    if problems:
        raise ValueError("\n".join(problems))


def _write_atomic(path: Path, text: str) -> None:
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _group_entries(args: argparse.Namespace) -> list[dict]:
    entries = read_list(args.list, allow_missing_expected=True)
    return [
        e
        for e in entries
        if (e["strategy"], e["n1"], e["n2"], e["n3"])
        == (args.strategy, args.n1, args.n2, args.n3)
    ]


def cmd_validate(args: argparse.Namespace) -> int:
    entries = read_list(args.list, allow_missing_expected=args.allow_missing_expected)
    validate_entries(entries)
    print(f"ok: {len(entries)} entries")
    return 0


def cmd_groups(args: argparse.Namespace) -> int:
    entries = read_list(args.list, allow_missing_expected=True)
    groups = sorted({(e["strategy"], e["n1"], e["n2"], e["n3"]) for e in entries})
    for strategy, n1, n2, n3 in groups:
        print(f"{strategy} {n1} {n2} {n3}")
    return 0


def cmd_datasets(args: argparse.Namespace) -> int:
    for name in sorted({e["data_name"] for e in _group_entries(args)}):
        print(name)
    return 0


def cmd_entries(args: argparse.Namespace) -> int:
    for e in _group_entries(args):
        if e["data_name"] == args.data_name:
            print(f"{e['fl_algo']} {e['seed']}")
    return 0


def cmd_field(args: argparse.Namespace) -> int:
    for e in _group_entries(args):
        if e["data_name"] == args.data_name and e["fl_algo"] == args.fl_algo:
            if args.name not in e:
                raise ValueError(f"entry has no {args.name}")
            _write_atomic(args.out, json.dumps(e[args.name]))
            return 0
    raise ValueError(
        f"no entry for {args.strategy} {args.n1} {args.n2} {args.n3} "
        f"{args.data_name} {args.fl_algo}"
    )


def cmd_compare(args: argparse.Namespace) -> int:
    with open(args.expected, "r") as f:
        expected = json.load(f)
    with open(args.actual, "r") as f:
        actual = json.load(f)
    diffs = diff_json(expected, actual)
    for line in diffs:
        print(line)
    if diffs:
        print(f"{len(diffs)} difference(s)", file=sys.stderr)
        return 1
    return 0


def parse_bands(text: str) -> list[tuple[str, int, int]]:
    try:
        edges = [int(x) for x in text.split(",")]
    except ValueError:
        raise ValueError(f"--bands must be comma-separated integers, got {text!r}")
    if len(edges) < 2 or any(a >= b for a, b in zip(edges, edges[1:])):
        raise ValueError(f"--bands needs at least two increasing edges, got {text!r}")
    return [(f"{lo}-{hi - 1}", lo, hi) for lo, hi in zip(edges, edges[1:])]


def _band_label(workers: int, bands: list[tuple[str, int, int]]) -> str:
    for label, lo, hi in bands:
        if lo <= workers < hi:
            return label
    return OTHER_BAND


def load_rows(
    csv_path: Path, bands: list[tuple[str, int, int]], datasets: set | None = None
) -> tuple[list, dict]:
    candidates = []
    universe = {
        "strategy": set(STRATEGIES),
        "fl_algo": set(),
        "dataset": set(datasets or ()),
    }
    seen = set()
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in CSV_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{csv_path}: missing columns {missing}")
        for row in reader:
            where = f"{csv_path}: row {reader.line_num}"
            try:
                repeat = int(row["repeat"])
                n1 = int(row["n_atnog_test1"])
                n2 = int(row["n_hobbit"])
                n3 = int(row["n_samwise"])
                workers = int(row["num_workers"])
                time_s = float(row["total_time_s"]) if row["total_time_s"] else None
            except ValueError as exc:
                raise ValueError(f"{where}: {exc}")
            if datasets is not None and row["dataset"] not in datasets:
                continue
            universe["strategy"].add(row["strategy"])
            universe["fl_algo"].add(row["fl_algo"])
            universe["dataset"].add(row["dataset"])
            if repeat != 1:
                continue
            cand = {
                "strategy": row["strategy"],
                "combo": row["combo"],
                "n1": n1,
                "n2": n2,
                "n3": n3,
                "workers": workers,
                "dataset": row["dataset"],
                "fl_algo": row["fl_algo"],
                "time": time_s,
                "band": _band_label(workers, bands),
            }
            if cand["strategy"] not in STRATEGIES:
                raise ValueError(f"{where}: unknown strategy {cand['strategy']!r}")
            if combo_of(cand) != cand["combo"]:
                raise ValueError(
                    f"{where}: combo {cand['combo']!r} does not match its node counts"
                )
            cand["id"] = (
                cand["strategy"],
                cand["combo"],
                cand["dataset"],
                cand["fl_algo"],
            )
            if cand["id"] in seen:
                raise ValueError(
                    f"{where}: duplicate repeat-1 row for {'/'.join(cand['id'])}"
                )
            seen.add(cand["id"])
            candidates.append(cand)
    candidates.sort(key=lambda c: c["id"])
    return candidates, universe


def _cover(
    cands: list[dict], universe: dict, bands: list, target: int, rng
) -> list[dict]:
    if not cands:
        raise ValueError("no repeat-1 candidate rows")
    min_w = min(c["workers"] for c in cands)
    max_w = max(c["workers"] for c in cands)
    required = {("workers", "min"), ("workers", "max")}
    for kind in ("strategy", "fl_algo", "dataset"):
        required |= {(kind, v) for v in universe[kind]}
    required |= {("band", label) for label, _, _ in bands}
    for c in cands:
        marg = {
            ("strategy", c["strategy"]),
            ("fl_algo", c["fl_algo"]),
            ("dataset", c["dataset"]),
            ("band", c["band"]),
        }
        if c["workers"] == min_w:
            marg.add(("workers", "min"))
        if c["workers"] == max_w:
            marg.add(("workers", "max"))
        c["marginals"] = frozenset(marg & required)
    reachable = set().union(*(c["marginals"] for c in cands))
    unreachable = sorted(required - reachable)
    if unreachable:
        names = ", ".join(f"{kind}={value}" for kind, value in unreachable)
        raise ValueError(f"no repeat-1 candidate covers: {names}")
    uncovered = set(required)
    picks = []
    while uncovered:
        best, best_n = [], 0
        for c in cands:
            n = len(c["marginals"] & uncovered)
            if n > best_n:
                best, best_n = [c], n
            elif n == best_n and n > 0:
                best.append(c)
        pick = rng.choice(best)
        picks.append(pick)
        uncovered -= pick["marginals"]
        if len(picks) > target:
            raise ValueError(
                f"--target {target} is smaller than the picks needed to cover "
                f"all {len(required)} marginal values"
            )
    return picks


def _fill(cands: list[dict], picks: list[dict], target: int, rng) -> list[dict]:
    picked_ids = {c["id"] for c in picks}
    remaining: dict[str, dict[tuple, list]] = {}
    for c in cands:
        if c["id"] in picked_ids:
            continue
        stratum = (c["strategy"], c["fl_algo"], c["band"])
        remaining.setdefault(c["dataset"], {}).setdefault(stratum, []).append(c)
    ds_counts: dict[str, int] = {}
    st_counts: dict[tuple, int] = {}
    for c in picks:
        ds_counts[c["dataset"]] = ds_counts.get(c["dataset"], 0) + 1
        key = (c["dataset"], c["strategy"], c["fl_algo"], c["band"])
        st_counts[key] = st_counts.get(key, 0) + 1
    picks = list(picks)
    while len(picks) < target:
        datasets = sorted(remaining)
        fewest = min(ds_counts.get(d, 0) for d in datasets)
        dataset = rng.choice([d for d in datasets if ds_counts.get(d, 0) == fewest])
        strata = sorted(remaining[dataset])
        low = min(st_counts.get((dataset, *s), 0) for s in strata)
        stratum = rng.choice(
            [s for s in strata if st_counts.get((dataset, *s), 0) == low]
        )
        pool = remaining[dataset][stratum]
        pick = rng.choice(pool)
        pool.remove(pick)
        if not pool:
            del remaining[dataset][stratum]
            if not remaining[dataset]:
                del remaining[dataset]
        picks.append(pick)
        ds_counts[dataset] = ds_counts.get(dataset, 0) + 1
        st_counts[(dataset, *stratum)] = low + 1
    return picks


def _entry_from(cand: dict) -> dict:
    return {
        "strategy": cand["strategy"],
        "n1": cand["n1"],
        "n2": cand["n2"],
        "n3": cand["n3"],
        "data_name": cand["dataset"],
        "fl_algo": cand["fl_algo"],
        "seed": REPEAT1_SEED,
    }


def _read_json(path: Path, problems: list[str], who: str) -> object:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        problems.append(f"{who}: missing file {path}")
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"{who}: cannot read {path}: {exc}")
    return None


def _embed_expected(entries: list[dict], results_dir: Path) -> None:
    problems: list[str] = []
    for entry in entries:
        who = "/".join(
            (entry["strategy"], combo_of(entry), entry["data_name"], entry["fl_algo"])
        )
        base = (
            Path(results_dir) / entry["strategy"] / combo_of(entry) / entry["data_name"]
        )
        hp_path = base / entry["fl_algo"] / "rep_1" / "hyperparameters.json"
        hp = _read_json(hp_path, problems, who)
        division = _read_json(base / "division.json", problems, who)
        if hp is not None:
            resampled = sample(entry["fl_algo"], key_of(entry))
            for line in diff_json(hp, resampled):
                problems.append(
                    f"{who}: hyperparameters.json vs current sampler: {line}"
                )
        if division is not None and not (
            isinstance(division, dict) and "worker_feature_entropy" in division
        ):
            problems.append(f"{who}: division.json has no worker_feature_entropy")
        entry["expected_hyperparameters"] = hp
        entry["expected_division"] = division
    if problems:
        raise ValueError("\n".join(problems))


def _summary(picks: list[dict], universe: dict, bands: list) -> dict:
    def counts(field: str, values) -> dict:
        return {v: sum(1 for c in picks if c[field] == v) for v in sorted(values)}

    labels = [label for label, _, _ in bands]
    if any(c["band"] == OTHER_BAND for c in picks):
        labels.append(OTHER_BAND)
    by_dataset_time: dict[str, float] = {d: 0.0 for d in sorted(universe["dataset"])}
    for c in picks:
        if c["time"] is not None:
            by_dataset_time[c["dataset"]] += c["time"]
    return {
        "n_picks": len(picks),
        "by_strategy": counts("strategy", universe["strategy"]),
        "by_fl_algo": counts("fl_algo", universe["fl_algo"]),
        "by_dataset": counts("dataset", universe["dataset"]),
        "by_band": {
            label: sum(1 for c in picks if c["band"] == label) for label in labels
        },
        "estimated_run_seconds": sum(by_dataset_time.values()),
        "estimated_run_seconds_by_dataset": by_dataset_time,
        "n_groups": len({(c["strategy"], c["combo"]) for c in picks}),
        "n_group_dataset_pairs": len(
            {(c["strategy"], c["combo"], c["dataset"]) for c in picks}
        ),
        "min_worker_total": min(c["workers"] for c in picks),
        "max_worker_total": max(c["workers"] for c in picks),
    }


def cmd_sample(args: argparse.Namespace) -> int:
    bands = parse_bands(args.bands)
    datasets = {d for d in args.datasets.split(",") if d} if args.datasets else None
    cands, universe = load_rows(args.csv, bands, datasets)
    if args.target < 1:
        raise ValueError("--target must be positive")
    if args.target > len(cands):
        raise ValueError(f"--target {args.target} exceeds the {len(cands)} candidates")
    rng = random.Random(args.seed)
    picks = _cover(cands, universe, bands, args.target, rng)
    picks = _fill(cands, picks, args.target, rng)
    picks.sort(key=lambda c: c["id"])
    entries = [_entry_from(c) for c in picks]
    if args.results_dir:
        _embed_expected(entries, Path(args.results_dir))
    ordered = [{f: e[f] for f in LIST_FIELDS if f in e} for e in entries]
    _write_atomic(args.out, "".join(json.dumps(e) + "\n" for e in ordered))
    if args.summary_out:
        _write_atomic(
            args.summary_out,
            json.dumps(_summary(picks, universe, bands), indent=2) + "\n",
        )
    print(f"wrote {len(ordered)} entries to {args.out}")
    return 0


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(1)


def _add_group(p: argparse.ArgumentParser) -> None:
    p.add_argument("--list", required=True, type=Path)
    p.add_argument("--strategy", required=True)
    p.add_argument("--n1", required=True, type=int)
    p.add_argument("--n2", required=True, type=int)
    p.add_argument("--n3", required=True, type=int)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(description="Noise-floor rerun list tools.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="check a rerun list")
    p.add_argument("--list", required=True, type=Path)
    p.add_argument("--allow-missing-expected", action="store_true")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("groups", help="print the distinct groups")
    p.add_argument("--list", required=True, type=Path)
    p.set_defaults(func=cmd_groups)

    p = sub.add_parser("datasets", help="print the datasets of a group")
    _add_group(p)
    p.set_defaults(func=cmd_datasets)

    p = sub.add_parser("entries", help="print fl_algo and seed per entry")
    _add_group(p)
    p.add_argument("--data-name", required=True)
    p.set_defaults(func=cmd_entries)

    p = sub.add_parser("field", help="write one expected_* object to a file")
    _add_group(p)
    p.add_argument("--data-name", required=True)
    p.add_argument("--fl-algo", required=True)
    p.add_argument("--name", required=True, choices=EXPECTED_FIELDS)
    p.add_argument("--out", required=True, type=Path)
    p.set_defaults(func=cmd_field)

    p = sub.add_parser("compare", help="diff two JSON files")
    p.add_argument("--expected", required=True, type=Path)
    p.add_argument("--actual", required=True, type=Path)
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("sample", help="draw the stratified rerun list")
    p.add_argument("--csv", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--results-dir", type=Path)
    p.add_argument("--target", type=int, default=150)
    p.add_argument("--seed", type=int, default=74)
    p.add_argument("--summary-out", type=Path)
    p.add_argument("--bands", default=DEFAULT_BANDS)
    p.add_argument("--datasets", help="comma-separated datasets to sample from")
    p.set_defaults(func=cmd_sample)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"noise_configs.py: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
