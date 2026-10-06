from copy import deepcopy

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
    assert document.isascii()


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
    with pytest.raises(ValueError):
        render(audit, sanity, sanity_prov, before, before_prov)
