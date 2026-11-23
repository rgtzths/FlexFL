#!/usr/bin/env python3
"""Pair original and rerun assembled CSVs and report the run-to-run noise floor."""

import argparse
import csv
import math
import statistics
import sys
from pathlib import Path

KEY_FIELDS = ("strategy", "combo", "dataset", "fl_algo")
HP_FIELDS = (
    "learning_rate",
    "batch_size",
    "local_epochs",
    "patience",
    "delta",
    "epoch_cap",
    "early_stop_on",
    "min_epochs",
)
TARGETS = (
    "performance",
    "total_time_s",
    "comm_bytes_total",
    "n_epochs",
    "compute_time_total_s",
    "compute_time_max_s",
    "comm_time_total_s",
    "comm_time_max_s",
    "serial_time_total_s",
    "validation_time_s",
)
COHORT_TARGET = "performance"
SUMMARY_COLUMNS = (
    "target",
    "cohort",
    "n_pairs",
    "n_excluded",
    "cv_median",
    "cv_mean",
    "cv_pooled",
    "r2_raw",
    "r2_log1p",
)
PAIR_COLUMNS = KEY_FIELDS + (
    "target",
    "cohort",
    "original",
    "rerun",
    "pair_cv",
    "reason",
)
REQUIRED_COLUMNS = KEY_FIELDS + ("repeat", "is_classification") + HP_FIELDS + TARGETS
NA = "NA"
TRUE_FLAGS = ("true", "1", "1.0")
FALSE_FLAGS = ("false", "0", "0.0")
MARKER = ".setup_complete"


class ReportError(Exception):
    pass


def parse_flag(text, where):
    value = text.strip().lower()
    if value in TRUE_FLAGS:
        return True
    if value in FALSE_FLAGS:
        return False
    raise ReportError(f"{where}: unreadable is_classification {text!r}")


def parse_number(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return math.nan


def finite_number(text):
    value = parse_number(text)
    return value if math.isfinite(value) else None


def read_repeat1(path, label):
    rows = {}
    with open(path, newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ReportError(f"{label} CSV lacks columns: {', '.join(missing)}")
        for line, row in enumerate(reader, start=2):
            if parse_number(row["repeat"]) != 1:
                continue
            key = tuple(row[field] for field in KEY_FIELDS)
            if key in rows:
                raise ReportError(
                    f"duplicate key in {label} CSV (line {line}): {'|'.join(key)}"
                )
            row["_cohort_flag"] = parse_flag(
                row["is_classification"], f"{label} CSV line {line}"
            )
            rows[key] = row
    return rows


def hp_value(text):
    text = text.strip()
    if text == "":
        return ("num", None)
    try:
        number = float(text)
    except ValueError:
        return ("str", text)
    return ("num", None if math.isnan(number) else number)


def hp_match(original, rerun):
    return all(hp_value(original[f]) == hp_value(rerun[f]) for f in HP_FIELDS)


def cohort_of(target, row):
    if target != COHORT_TARGET:
        return "all"
    return "classification" if row["_cohort_flag"] else "regression"


def fmt(value):
    return NA if value is None else repr(float(value))


def r_squared(truth, pred):
    if len(truth) < 2 or len(set(truth)) == 1:
        return None
    mean = sum(truth) / len(truth)
    ss_tot = sum((t - mean) ** 2 for t in truth)
    if ss_tot == 0:
        return None
    ss_res = sum((t - p) ** 2 for t, p in zip(truth, pred))
    return 1 - ss_res / ss_tot


def summarize(records, n_excluded):
    originals = [r["original"] for r in records]
    reruns = [r["rerun"] for r in records]
    usable = [(a, b) for a, b in zip(originals, reruns) if (a + b) != 0]
    cvs = [abs(a - b) / math.sqrt(2) / abs((a + b) / 2) for a, b in usable]
    out = {
        "cv_median": statistics.median(cvs) if cvs else None,
        "cv_mean": statistics.fmean(cvs) if cvs else None,
        "cv_pooled": None,
        "r2_raw": r_squared(originals, reruns),
        "r2_log1p": None,
    }
    if usable:
        variances = [(a - b) ** 2 / 2 for a, b in usable]
        mean_abs = statistics.fmean(abs((a + b) / 2) for a, b in usable)
        if mean_abs != 0:
            out["cv_pooled"] = math.sqrt(statistics.fmean(variances)) / mean_abs
    if originals and min(originals + reruns) >= 0:
        out["r2_log1p"] = r_squared(
            [math.log1p(v) for v in originals], [math.log1p(v) for v in reruns]
        )
    out["n_pairs"] = len(records)
    out["n_excluded"] = n_excluded
    return out


def pair_cv(a, b):
    if a + b == 0:
        return None
    return abs(a - b) / math.sqrt(2) / abs((a + b) / 2)


def check_out_dir(out_dir):
    resolved = out_dir.resolve()
    for folder in (resolved, *resolved.parents):
        if (folder / MARKER).exists():
            raise ReportError(f"refusing --out-dir: {folder / MARKER} exists")
    if resolved.is_dir() and any(resolved.rglob(MARKER)):
        raise ReportError(f"refusing --out-dir: {MARKER} found beneath {resolved}")


def build(original_rows, rerun_rows):
    pair_rows = []
    groups = {}
    for key in sorted(set(original_rows) | set(rerun_rows)):
        original, rerun = original_rows.get(key), rerun_rows.get(key)
        source = original if original is not None else rerun
        if original is None:
            reason = "missing_original"
        elif rerun is None:
            reason = "missing_rerun"
        elif not hp_match(original, rerun):
            reason = "hp_mismatch"
        else:
            reason = "included"
        for target in TARGETS:
            cohort = cohort_of(target, source)
            bucket = groups.setdefault((target, cohort), {"pairs": [], "excluded": 0})
            a = finite_number(original[target]) if original is not None else None
            b = finite_number(rerun[target]) if rerun is not None else None
            row_reason = reason
            if reason == "included" and (a is None or b is None):
                row_reason = "missing_value"
            cv = pair_cv(a, b) if row_reason == "included" else None
            if row_reason == "included":
                bucket["pairs"].append({"original": a, "rerun": b})
            elif row_reason != "missing_original":
                bucket["excluded"] += 1
            pair_rows.append(
                dict(
                    zip(KEY_FIELDS, key),
                    target=target,
                    cohort=cohort,
                    original=fmt(a),
                    rerun=fmt(b),
                    pair_cv=fmt(cv),
                    reason=row_reason,
                )
            )
    summary_rows = []
    for target in TARGETS:
        cohorts = (
            ("classification", "regression") if target == COHORT_TARGET else ("all",)
        )
        for cohort in cohorts:
            bucket = groups.get((target, cohort), {"pairs": [], "excluded": 0})
            stats = summarize(bucket["pairs"], bucket["excluded"])
            summary_rows.append(
                {
                    "target": target,
                    "cohort": cohort,
                    "n_pairs": stats["n_pairs"],
                    "n_excluded": stats["n_excluded"],
                    **{
                        name: fmt(stats[name])
                        for name in (
                            "cv_median",
                            "cv_mean",
                            "cv_pooled",
                            "r2_raw",
                            "r2_log1p",
                        )
                    },
                }
            )
    return summary_rows, pair_rows


def write_csv(path, columns, rows):
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True)
    parser.add_argument("--rerun", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)
    out_dir = Path(args.out_dir)
    try:
        check_out_dir(out_dir)
        original_rows = read_repeat1(args.original, "original")
        rerun_rows = read_repeat1(args.rerun, "rerun")
    except (ReportError, OSError) as error:
        print(f"noise_report.py: {error}", file=sys.stderr)
        return 2
    summary_rows, pair_rows = build(original_rows, rerun_rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "noise_summary.csv", SUMMARY_COLUMNS, summary_rows)
    write_csv(out_dir / "noise_pairs.csv", PAIR_COLUMNS, pair_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
