import json
from copy import deepcopy
from pathlib import Path

import pytest


def _inputs():
    rows = [
        {
            "dataset": "reg_num_synthetic",
            "tier20": False,
            "task": "reg",
            "n_train": 180,
            "n_feat": 3,
            "max_abs_z": 4.5,
            "n_feat_z_gt10": 0,
            "n_all_sentinel_rows": 0,
            "frac_dup_rows_train": 0.012,
            "frac_dup_label_conflict": 0.0,
            "y_skew": 1.234,
            "flags": "",
        },
        {
            "dataset": "clf_num_MiniBooNE",
            "tier20": True,
            "task": "clf",
            "n_train": 43798,
            "n_feat": 50,
            "max_abs_z": 12.3,
            "n_feat_z_gt10": 2,
            "n_all_sentinel_rows": 173,
            "frac_dup_rows_train": 0.023,
            "frac_dup_label_conflict": 0.004,
            "imbalance_ratio": 2.345,
            "flags": "all_sentinel_rows",
        },
    ]
    sanity = [
        {
            "dataset": "clf_num_MiniBooNE",
            "keep_sentinel_rows": False,
            "constant": 0.111,
            "hgb": 0.222,
            "standard_lr0.001": {"best": 0.865},
            "clip_lr0.001": {"best": 0.444},
            "quantile_lr0.001": {"best": 0.555},
            "standard_lr0.0001": {"best": 0.666},
        },
        {
            "dataset": "reg_num_synthetic",
            "keep_sentinel_rows": False,
            "constant": 1.111,
            "hgb": 1.222,
            "standard_lr0.001": {"best": 1.333},
            "clip_lr0.001": {"best": 1.444},
            "quantile_lr0.001": {"best": 1.555},
            "standard_lr0.0001": {"best": 1.666},
        },
    ]
    prov = {
        "hf_revision": "rev1",
        "sources_sha256": {"scripts/audit_datasets.py": "source-hash"},
    }
    sanity_prov = {
        **deepcopy(prov),
        "run_constants": {
            "MAX_TRAIN": 100000,
            "EPOCHS": 40,
            "PATIENCE": 8,
            "BATCH": 512,
            "LRS": [0.001, 0.0001],
            "SEED": 42,
        },
        "hpo_sha256": {"clf_num_MiniBooNE": "hpo-hash"},
        "keep_sentinel_rows": False,
    }
    before = [deepcopy(sanity[0])]
    before[0]["keep_sentinel_rows"] = True
    before[0]["standard_lr0.001"]["best"] = 0.836
    before_prov = deepcopy(sanity_prov)
    before_prov["keep_sentinel_rows"] = True
    return {"provenance": prov, "rows": rows}, sanity, sanity_prov, before, before_prov


def _cells(table):
    return [
        [cell.strip() for cell in line.split("|")[1:-1]]
        for line in table.splitlines()[2:]
    ]


def test_render_main_round_trip(tmp_path):
    import render_dataset_audit

    audit, sanity, sanity_prov, before, before_prov = _inputs()
    audit_path = tmp_path / "audit.json"
    sanity_path = tmp_path / "sanity.jsonl"
    before_path = tmp_path / "before.jsonl"
    output = tmp_path / "report.md"
    audit_path.write_text(json.dumps(audit))
    for path, records, prov in (
        (sanity_path, sanity, sanity_prov),
        (before_path, before, before_prov),
    ):
        path.write_text("".join(json.dumps(record) + "\n" for record in records))
        Path(f"{path}.provenance.json").write_text(json.dumps(prov))
    render_dataset_audit.main(
        [
            "--audit-json",
            str(audit_path),
            "--sanity",
            str(sanity_path),
            "--sanity-before",
            str(before_path),
            "--out",
            str(output),
        ]
    )
    assert output.read_text() == render_dataset_audit.render(*_inputs())


def test_render_tables_preserve_dataset_names_and_metric_columns():
    from render_dataset_audit import render, sanity_table, static_table

    inputs = _inputs()
    audit, sanity, _, _, _ = inputs
    static = _cells(static_table(audit["rows"]))
    assert [row[0] for row in static] == ["clf_num_MiniBooNE", "reg_num_synthetic"]
    assert static[0][1:] == [
        "yes",
        "clf",
        "43798",
        "50",
        "12.30",
        "2",
        "173",
        "2.3%",
        "0.4%",
        "2.35",
        "all_sentinel_rows",
        "standard scaling; drop all -999 rows (173)",
    ]
    assert static[1][1:] == [
        "",
        "reg",
        "180",
        "3",
        "4.50",
        "0",
        "0",
        "1.2%",
        "0.0%",
        "1.23",
        "",
        "standard scaling",
    ]
    assert _cells(sanity_table(sanity)) == [
        [
            "clf_num_MiniBooNE",
            "MCC",
            "0.111",
            "0.222",
            "0.865",
            "0.444",
            "0.555",
            "0.666",
        ],
        [
            "reg_num_synthetic",
            "SMAPE",
            "1.111",
            "1.222",
            "1.333",
            "1.444",
            "1.555",
            "1.666",
        ],
    ]
    document = render(*inputs)
    assert document.startswith("# Dataset preprocessing audit\n")
    assert document.count('"hf_revision": "rev1"') >= 2
    assert "with sentinel rows: 0.836; without sentinel rows: 0.865" in document
    assert "training-split statistics (T068)" in document
    assert "regression targets likewise (T069)" in document
    assert "2026-10-05" in document
    assert "outside `results/`" in document
    assert "--keep-sentinel-rows" in document
    assert "every sanity dataset except reg_num_synthetic" in document
    assert "does not beat the constant baseline on reg_num_synthetic either" in document
    assert "clf_num_MiniBooNE (173)" in document
    assert "best validation score over at most 40 epochs (patience 8)" in document
    assert "--hpo-dir results/hyperparameter_optimization" in document
    assert "mktemp -d" in document
    assert "Run the scripts from the repository root" in document
    assert "~/" not in document
    assert document.isascii()
    assert (
        "revision 8d0ff9103525b7e3579b180230fddb3186258301 "
        "in the local Hugging Face cache"
    ) in document


@pytest.mark.parametrize(
    "mismatch",
    [
        "audit_revision",
        "before_revision",
        "audit_sources",
        "before_sources",
        "constants",
        "hpo",
        "swapped",
        "sanity_record",
        "before_record",
        "sanity_sidecar",
        "before_sidecar",
        "missing_sanity_record",
        "missing_before_record",
        "missing_sanity_sidecar",
        "missing_before_sidecar",
        "rationale",
    ],
)
def test_render_rejects_incompatible_evidence(mismatch):
    from render_dataset_audit import render

    audit, sanity, sanity_prov, before, before_prov = _inputs()
    if mismatch == "audit_revision":
        audit["provenance"]["hf_revision"] = "rev2"
    elif mismatch == "before_revision":
        before_prov["hf_revision"] = "rev2"
    elif mismatch == "audit_sources":
        audit["provenance"]["sources_sha256"] = {"other": "hash"}
    elif mismatch == "before_sources":
        before_prov["sources_sha256"] = {"other": "hash"}
    elif mismatch == "constants":
        before_prov["run_constants"]["SEED"] = 7
    elif mismatch == "hpo":
        before_prov["hpo_sha256"]["clf_num_MiniBooNE"] = "different"
    elif mismatch == "swapped":
        sanity, before = before, sanity
        sanity_prov, before_prov = before_prov, sanity_prov
    elif mismatch == "sanity_record":
        sanity[0]["keep_sentinel_rows"] = True
    elif mismatch == "before_record":
        before[0]["keep_sentinel_rows"] = False
    elif mismatch == "sanity_sidecar":
        sanity_prov["keep_sentinel_rows"] = True
    elif mismatch == "before_sidecar":
        before_prov["keep_sentinel_rows"] = False
    elif mismatch == "missing_sanity_record":
        del sanity[0]["keep_sentinel_rows"]
    elif mismatch == "missing_before_record":
        del before[0]["keep_sentinel_rows"]
    elif mismatch == "missing_sanity_sidecar":
        del sanity_prov["keep_sentinel_rows"]
    elif mismatch == "missing_before_sidecar":
        del before_prov["keep_sentinel_rows"]
    elif mismatch == "rationale":
        sanity[1]["hgb"] = 1.0
    with pytest.raises(ValueError):
        render(audit, sanity, sanity_prov, before, before_prov)


def test_render_states_none_when_nothing_misses():
    from render_dataset_audit import render

    audit, sanity, sanity_prov, before, before_prov = _inputs()
    sanity[1]["standard_lr0.001"]["best"] = 1.0
    sanity[1]["hgb"] = 1.0
    audit["rows"][1]["n_all_sentinel_rows"] = 0
    document = render(audit, sanity, sanity_prov, before, before_prov)
    assert "every sanity dataset except none." in document
    assert "constant baseline on none either" in document
    assert "counted over train, val and test, for: none." in document
    assert "delete `data/<name>/_data` for none on any host" in document


def test_render_pairs_each_dropped_dataset_with_its_count():
    from render_dataset_audit import render

    audit, sanity, sanity_prov, before, before_prov = _inputs()
    audit["rows"][0]["n_all_sentinel_rows"] = 500
    document = render(audit, sanity, sanity_prov, before, before_prov)
    assert "for: clf_num_MiniBooNE (173), reg_num_synthetic (500)." in document
    assert (
        "delete `data/<name>/_data` for clf_num_MiniBooNE, reg_num_synthetic on any"
        in document
    )
