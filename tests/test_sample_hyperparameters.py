import json
import subprocess
import sys
from pathlib import Path

import pytest
from sample_hyperparameters import sample

KEY = "atnog-test1_2_hobbit_2_samwise_2|clf_cat_compas-two-years|{}"
DRAWN = {
    "CentralizedSync": {
        "learning_rate": 0.000117,
        "batch_size": 2048,
        "patience": 4,
        "delta": 0.0124,
    },
    "CentralizedAsync": {
        "learning_rate": 0.002524,
        "batch_size": 256,
        "patience": 6,
        "delta": 0.01417,
    },
    "DecentralizedSync": {
        "learning_rate": 0.002232,
        "batch_size": 256,
        "patience": 6,
        "delta": 0.00139,
        "local_epochs": 8,
    },
    "DecentralizedAsync": {
        "learning_rate": 0.000632,
        "batch_size": 512,
        "patience": 9,
        "delta": 0.01355,
        "local_epochs": 2,
    },
}


FIXED = {"epochs": 200, "early_stop_on": "loss", "min_epochs": 10}


@pytest.mark.parametrize("algo", sorted(DRAWN))
def test_sample_adds_the_fixed_cap_and_rule_without_changing_the_draws(algo):
    assert sample(algo, KEY.format(algo)) == {**DRAWN[algo], **FIXED}


def test_cli_passes_and_records_the_cap_and_rule(tmp_path):
    out = tmp_path / "hp.json"
    script = str(
        Path(__file__).resolve().parent.parent / "scripts" / "sample_hyperparameters.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            script,
            "--algo",
            "DecentralizedSync",
            "--key",
            KEY.format("DecentralizedSync"),
            "--json-out",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == (
        "--learning_rate 0.002232 --batch_size 256 --patience 6 --delta 0.00139"
        " --local_epochs 8 --epochs 200"
        " --early_stop_on loss --min_epochs 10"
    )
    assert json.loads(out.read_text()) == {**DRAWN["DecentralizedSync"], **FIXED}
