#!/usr/bin/env python3
"""Render audit and sanity evidence into the Markdown preprocessing report.

Reads audit JSON, sanity JSONL and provenance sidecars, refuses incompatible
evidence, and writes Markdown. Run from the repository root:

    .venv/bin/python scripts/render_dataset_audit.py --audit-json audit.json \
        --sanity sanity.jsonl --sanity-before before.jsonl --out report.md
"""

import argparse
import json
from pathlib import Path

from audit_common import HEADLINE_KEY, LRS, better, read_lines, score_key

from flexfl.datasets.Benchmark import HF_REVISION, SENTINEL, is_clf

MINIBOONE = "clf_num_MiniBooNE"
SENTINEL_TEXT = f"{SENTINEL:g}"
SANITY_COLUMNS = (
    ("standard (1e-3)", HEADLINE_KEY),
    ("clip (1e-3)", score_key("clip", LRS[0])),
    ("quantile (1e-3)", score_key("quantile", LRS[0])),
    ("standard (1e-4)", score_key("standard", LRS[1])),
)
REPRODUCE = (
    "out=$(mktemp -d)\n"
    'sed -n "/^datasets=(/,/^)/p" scripts/run_full_experiments.sh '
    '| tr -d "\'" | grep -v \'[()]\' > "$out"/names.txt\n'
    ".venv/bin/python scripts/select_dataset_tiers.py --tier 20 "
    '< "$out"/names.txt > "$out"/tier20.txt\n'
    f"printf '%s\\n' {MINIBOONE} > \"$out\"/miniboone.txt\n"
    '.venv/bin/python scripts/audit_datasets.py --names "$out"/names.txt '
    '--tier20 "$out"/tier20.txt --out-json "$out"/dataset_audit.json '
    '--out-csv "$out"/dataset_audit.csv\n'
    "uv sync --frozen --extra ml\n"
    '.venv/bin/python scripts/audit_central_sanity.py --names "$out"/tier20.txt '
    "--hpo-dir results/hyperparameter_optimization "
    '--out "$out"/central_sanity.jsonl\n'
    '.venv/bin/python scripts/audit_central_sanity.py --names "$out"/miniboone.txt '
    "--hpo-dir results/hyperparameter_optimization --keep-sentinel-rows "
    '--out "$out"/central_sanity_keep_sentinel.jsonl\n'
    "uv sync --frozen\n"
    'cp "$out"/dataset_audit.json "$out"/dataset_audit.csv '
    '"$out"/central_sanity.jsonl "$out"/central_sanity.jsonl.provenance.json '
    '"$out"/central_sanity_keep_sentinel.jsonl '
    '"$out"/central_sanity_keep_sentinel.jsonl.provenance.json docs/audit/\n'
    ".venv/bin/python scripts/render_dataset_audit.py "
    "--audit-json docs/audit/dataset_audit.json "
    "--sanity docs/audit/central_sanity.jsonl "
    "--sanity-before docs/audit/central_sanity_keep_sentinel.jsonl "
    "--out docs/dataset_preprocessing_audit.md"
)


def _join(items):
    return ", ".join(sorted(items)) or "none"


def _intro(network_misses, reference_misses, epochs, patience, dropped):
    return (
        "Features are standardized with training-split statistics (T068) "
        "and regression targets likewise (T069).",
        "Keep standard scaling for every dataset. Rows whose features are all "
        f"{SENTINEL_TEXT} are dropped at preprocessing. No HPO re-tune.",
        "Worker-feature entropy before and after T068 is not comparable, so "
        "the meta-dataset is built only from runs gathered after the T068 "
        "relaunch on 2026-10-05, and older corpora stay archived "
        "outside `results/`.",
        "No HPO re-tune: at learning rate 1e-3 the tuned network beats the constant "
        f"baseline on every sanity dataset except {_join(network_misses)}. "
        "The boosting reference does not beat the constant baseline on "
        f"{_join(reference_misses)} either, so the metric carries little signal there.",
        f"Network scores are the best validation score over at most {epochs} epochs "
        f"(patience {patience}), so they are optimistic against the boosting "
        "reference, "
        "which has no selection.",
        f"The static audit describes raw rows before the all {SENTINEL_TEXT} drop, "
        f"so its row counts include the all {SENTINEL_TEXT} rows, counted over train, "
        "val and test, for: "
        f"{_join(f'{name} ({count})' for name, count in dropped.items())}.",
        "The sweep reuses any `data/<name>/_data` cache that holds `scaling.json`. "
        f"Before the tier-20 pass, delete `data/<name>/_data` for {_join(dropped)} "
        "on any "
        "host where that cache holds `scaling.json` and was built before the drop, "
        "so preprocessing runs again.",
        f"Run the scripts from the repository root. The all {SENTINEL_TEXT} drop "
        "applies to the Benchmark datasets only. The HPO configs come from "
        "results/hyperparameter_optimization, which is not tracked. "
        "A first-time preprocess needs network access to the Hugging Face Hub or "
        f"revision {HF_REVISION} in the local Hugging Face cache.",
    )


def _table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(map(str, row)) + " |" for row in rows)
    return "\n".join(lines)


def static_table(rows):
    headers = [
        "dataset",
        "tier 20",
        "task",
        "train rows",
        "features",
        "max abs z",
        "features with abs z above 10",
        f"all {SENTINEL_TEXT} rows",
        "duplicate train rows",
        "label conflicts",
        "imbalance ratio / target skew",
        "flags",
        "action",
    ]
    values = []
    for row in sorted(rows, key=lambda row: row["dataset"]):
        count = row["n_all_sentinel_rows"]
        action = "standard scaling"
        if count > 0:
            action += f"; drop all {SENTINEL_TEXT} rows ({count})"
        target = row["imbalance_ratio"] if row["task"] == "clf" else row["y_skew"]
        values.append(
            [
                row["dataset"],
                "yes" if row["tier20"] else "",
                row["task"],
                row["n_train"],
                row["n_feat"],
                f"{row['max_abs_z']:.2f}",
                row["n_feat_z_gt10"],
                count,
                f"{row['frac_dup_rows_train']:.1%}",
                f"{row['frac_dup_label_conflict']:.1%}",
                f"{target:.2f}",
                row["flags"],
                action,
            ]
        )
    return _table(headers, values)


def sanity_table(records):
    headers = [
        "dataset",
        "metric",
        "constant",
        "boosting reference",
        *(header for header, _ in SANITY_COLUMNS),
    ]
    values = []
    for record in records:
        scores = [record["constant"], record["hgb"]]
        scores.extend(record[key]["best"] for _, key in SANITY_COLUMNS)
        values.append(
            [
                record["dataset"],
                "MCC" if is_clf(record["dataset"]) else "SMAPE",
                *(f"{score:.3f}" for score in scores),
            ]
        )
    return _table(headers, values)


def _best(records, name):
    return next(record for record in records if record["dataset"] == name)[
        HEADLINE_KEY
    ]["best"]


def _beats(record, value):
    return better(is_clf(record["dataset"]), value, record["constant"])


def _validate(audit, sanity, sanity_prov, before, before_prov):
    for key in ("hf_revision", "sources_sha256"):
        if not (audit["provenance"][key] == sanity_prov[key] == before_prov[key]):
            raise ValueError(f"Provenance differs in {key}")
    if sanity_prov["run_constants"] != before_prov["run_constants"]:
        raise ValueError("Run constants differ")
    if sanity_prov["hpo_sha256"][MINIBOONE] != before_prov["hpo_sha256"][MINIBOONE]:
        raise ValueError("MiniBooNE HPO config hashes differ")
    for records, prov, keep in (
        (sanity, sanity_prov, False),
        (before, before_prov, True),
    ):
        if prov.get("keep_sentinel_rows") is not keep:
            raise ValueError("Sidecar keep_sentinel_rows conflicts with the run")
        if any(r.get("keep_sentinel_rows") is not keep for r in records):
            raise ValueError("Record keep_sentinel_rows conflicts with the run")


def render(audit, sanity, sanity_prov, before, before_prov):
    _validate(audit, sanity, sanity_prov, before, before_prov)
    after_score = _best(sanity, MINIBOONE)
    before_score = _best(before, MINIBOONE)
    network_misses = {
        row["dataset"] for row in sanity if not _beats(row, row[HEADLINE_KEY]["best"])
    }
    reference_misses = {row["dataset"] for row in sanity if not _beats(row, row["hgb"])}
    dropped = {
        row["dataset"]: row["n_all_sentinel_rows"]
        for row in audit["rows"]
        if row["n_all_sentinel_rows"] > 0
    }
    if not network_misses.issubset(reference_misses):
        raise ValueError(
            "No-re-tune rationale no longer holds: "
            + ", ".join(sorted(network_misses - reference_misses))
        )
    return (
        "\n\n".join(
            [
                "# Dataset preprocessing audit",
                *_intro(
                    network_misses,
                    reference_misses,
                    sanity_prov["run_constants"]["EPOCHS"],
                    sanity_prov["run_constants"]["PATIENCE"],
                    dropped,
                ),
                "## Audit provenance",
                "```json\n" + json.dumps(audit["provenance"], indent=2) + "\n```",
                "## Central sanity provenance",
                "```json\n"
                + json.dumps({"after": sanity_prov, "before": before_prov}, indent=2)
                + "\n```",
                "## Static audit",
                static_table(audit["rows"]),
                "## Central sanity",
                sanity_table(sanity),
                "MiniBooNE standard MCC at 1e-3, "
                f"with sentinel rows: {before_score:.3f}; "
                f"without sentinel rows: {after_score:.3f}.",
                "## Reproduce",
                "Outputs go to a scratch directory first, because the scripts record "
                "git_dirty and files written inside the tree would mark the next "
                "run dirty.",
                "```bash\n" + REPRODUCE + "\n```",
            ]
        )
        + "\n"
    )


def _read_records(path):
    return [json.loads(line) for line in read_lines(path)]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-json", type=Path, required=True)
    parser.add_argument("--sanity", type=Path, required=True)
    parser.add_argument("--sanity-before", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    document = render(
        json.loads(args.audit_json.read_text()),
        _read_records(args.sanity),
        json.loads(Path(f"{args.sanity}.provenance.json").read_text()),
        _read_records(args.sanity_before),
        json.loads(Path(f"{args.sanity_before}.provenance.json").read_text()),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(document)


if __name__ == "__main__":
    main()
