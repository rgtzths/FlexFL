import argparse
import json
from pathlib import Path


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
        "all -999 rows",
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
            action += f"; drop all -999 rows ({count})"
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
        "standard (1e-3)",
        "clip (1e-3)",
        "quantile (1e-3)",
        "standard (1e-4)",
    ]
    values = []
    for r in records:
        scores = [r["constant"], r["hgb"]]
        scores.extend(
            r[k]["best"]
            for k in (
                "standard_lr0.001",
                "clip_lr0.001",
                "quantile_lr0.001",
                "standard_lr0.0001",
            )
        )
        values.append(
            [
                r["dataset"],
                "MCC" if r["dataset"].startswith("clf_") else "SMAPE",
                *(f"{score:.3f}" for score in scores),
            ]
        )
    return _table(headers, values)


def _validate(audit, sanity, sanity_prov, before, before_prov):
    for key in ("hf_revision", "sources_sha256"):
        if not (audit["provenance"][key] == sanity_prov[key] == before_prov[key]):
            raise ValueError(f"Provenance differs in {key}")
    if sanity_prov["run_constants"] != before_prov["run_constants"]:
        raise ValueError("Run constants differ")
    name = "clf_num_MiniBooNE"
    if sanity_prov["hpo_sha256"][name] != before_prov["hpo_sha256"][name]:
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
    name = "clf_num_MiniBooNE"
    after_score = next(r for r in sanity if r["dataset"] == name)["standard_lr0.001"][
        "best"
    ]
    before_score = next(r for r in before if r["dataset"] == name)["standard_lr0.001"][
        "best"
    ]
    commands = (
        'sed -n "/^datasets=(/,/^)/p" scripts/run_full_experiments.sh '
        "| tr -d \"'\" | grep -v '[()]' > names.txt\n"
        ".venv/bin/python scripts/select_dataset_tiers.py --tier 20 "
        "< names.txt > tier20.txt\n"
        "printf '%s\\n' clf_num_MiniBooNE > miniboone.txt\n"
        ".venv/bin/python scripts/audit_datasets.py --names names.txt "
        "--tier20 tier20.txt --out-json docs/audit/dataset_audit.json "
        "--out-csv docs/audit/dataset_audit.csv\n"
        "uv sync --frozen --extra ml\n"
        ".venv/bin/python scripts/audit_central_sanity.py --names tier20.txt "
        "--hpo-dir ~/research/pkdd26_cost_modeling/FlexFL/results/"
        "hyperparameter_optimization --out docs/audit/central_sanity.jsonl\n"
        ".venv/bin/python scripts/audit_central_sanity.py --names miniboone.txt "
        "--hpo-dir ~/research/pkdd26_cost_modeling/FlexFL/results/"
        "hyperparameter_optimization --keep-sentinel-rows "
        "--out docs/audit/central_sanity_keep_sentinel.jsonl\n"
        "uv sync --frozen\n"
        ".venv/bin/python scripts/render_dataset_audit.py "
        "--audit-json docs/audit/dataset_audit.json "
        "--sanity docs/audit/central_sanity.jsonl "
        "--sanity-before docs/audit/central_sanity_keep_sentinel.jsonl "
        "--out docs/dataset_preprocessing_audit.md"
    )
    return (
        "\n\n".join(
            [
                "# Dataset preprocessing audit",
                "Features are standardized with training-split statistics (T068) "
                "and regression targets likewise (T069).",
                "Keep standard scaling for every dataset. Rows whose features are all "
                "-999 are dropped at preprocessing. No HPO re-tune.",
                "Worker-feature entropy before and after T068 is not comparable, so "
                "the meta-dataset is built only from runs gathered after the T068 "
                "relaunch on 2026-10-05, and older corpora stay archived "
                "outside `results/`.",
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
                "```bash\n" + commands + "\n```",
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
