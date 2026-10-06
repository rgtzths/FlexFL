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

from audit_central_sanity import LRS, score_key
from audit_datasets import is_clf

from flexfl.datasets.Benchmark import SENTINEL

MINIBOONE = "clf_num_MiniBooNE"
SENTINEL_TEXT = f"{SENTINEL:g}"
SANITY_COLUMNS = (
    ("standard (1e-3)", score_key("standard", LRS[0])),
    ("clip (1e-3)", score_key("clip", LRS[0])),
    ("quantile (1e-3)", score_key("quantile", LRS[0])),
    ("standard (1e-4)", score_key("standard", LRS[1])),
)
INTRO = (
    "Features are standardized with training-split statistics (T068) "
    "and regression targets likewise (T069).",
    "Keep standard scaling for every dataset. Rows whose features are all "
    f"{SENTINEL_TEXT} are dropped at preprocessing. No HPO re-tune.",
    "Worker-feature entropy before and after T068 is not comparable, so "
    "the meta-dataset is built only from runs gathered after the T068 "
    "relaunch on 2026-10-05, and older corpora stay archived "
    "outside `results/`.",
    "No HPO re-tune: at learning rate 1e-3 the tuned network beats the constant "
    "baseline on every sanity dataset except {network_misses}. The boosting "
    "reference does not beat the constant baseline on {reference_misses} either, "
    "so the metric carries little signal there.",
    "Network scores are the best validation score over at most {epochs} epochs "
    "(patience {patience}), so they are optimistic against the boosting reference, "
    "which has no selection.",
    f"The static audit describes raw rows before the all {SENTINEL_TEXT} drop, "
    f"so its row counts include the all {SENTINEL_TEXT} rows, counted over train, "
    "val and test, for: {dropped}.",
    "The sweep reuses any `data/<name>/_data` cache that holds `scaling.json`. "
    "Before the tier-20 pass, delete `data/<name>/_data` for {drop_names} on any "
    "host where that cache holds `scaling.json` and was built before the drop, "
    "so preprocessing runs again.",
    f"Run the scripts from the repository root. The all {SENTINEL_TEXT} drop "
    "applies to the Benchmark datasets only. The HPO configs come from "
    "results/hyperparameter_optimization, which is not tracked.",
)
REPRODUCE = (
    "out=$(mktemp -d)\n"
    'sed -n "/^datasets=(/,/^)/p" scripts/run_full_experiments.sh '
    '| tr -d "\'" | grep -v \'[()]\' > "$out"/names.txt\n'
    ".venv/bin/python scripts/select_dataset_tiers.py --tier 20 "
    '< "$out"/names.txt > "$out"/tier20.txt\n'
    "printf '%s\\n' clf_num_MiniBooNE > \"$out\"/miniboone.txt\n"
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
    for r in sorted(rows, key=lambda row: row["dataset"]):
        count = r["n_all_sentinel_rows"]
        action = "standard scaling"
        if count > 0:
            action += f"; drop all {SENTINEL_TEXT} rows ({count})"
        target = r["imbalance_ratio"] if r["task"] == "clf" else r["y_skew"]
        values.append(
            [
                r["dataset"],
                "yes" if r["tier20"] else "",
                r["task"],
                r["n_train"],
                r["n_feat"],
                f"{r['max_abs_z']:.2f}",
                r["n_feat_z_gt10"],
                count,
                f"{r['frac_dup_rows_train']:.1%}",
                f"{r['frac_dup_label_conflict']:.1%}",
                f"{target:.2f}",
                r["flags"],
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
    for r in records:
        scores = [r["constant"], r["hgb"]]
        scores.extend(r[key]["best"] for _, key in SANITY_COLUMNS)
        values.append(
            [
                r["dataset"],
                "MCC" if is_clf(r["dataset"]) else "SMAPE",
                *(f"{score:.3f}" for score in scores),
            ]
        )
    return _table(headers, values)


def _best(records, name):
    return next(r for r in records if r["dataset"] == name)[SANITY_COLUMNS[0][1]][
        "best"
    ]


def _beats(record, value):
    return (
        value > record["constant"]
        if is_clf(record["dataset"])
        else value < record["constant"]
    )


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
        r["dataset"] for r in sanity if not _beats(r, r[SANITY_COLUMNS[0][1]]["best"])
    }
    reference_misses = {r["dataset"] for r in sanity if not _beats(r, r["hgb"])}
    dropped = [
        (r["dataset"], r["n_all_sentinel_rows"])
        for r in audit["rows"]
        if r["n_all_sentinel_rows"] > 0
    ]
    if not network_misses.issubset(reference_misses):
        raise ValueError(
            "No-re-tune rationale no longer holds: "
            + ", ".join(sorted(network_misses - reference_misses))
        )
    return (
        "\n\n".join(
            [
                "# Dataset preprocessing audit",
                *(
                    paragraph.format(
                        network_misses=", ".join(sorted(network_misses)) or "none",
                        reference_misses=", ".join(sorted(reference_misses)) or "none",
                        epochs=sanity_prov["run_constants"]["EPOCHS"],
                        patience=sanity_prov["run_constants"]["PATIENCE"],
                        dropped=", ".join(
                            f"{name} ({count})" for name, count in sorted(dropped)
                        )
                        or "none",
                        drop_names=", ".join(sorted(name for name, _ in dropped))
                        or "none",
                    )
                    for paragraph in INTRO
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
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


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
