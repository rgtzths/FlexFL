import json
import math
import random
import subprocess
import sys
from pathlib import Path

import pytest
from sample_hyperparameters import sample, seed_from_key

KEY = "atnog-test1_2_hobbit_2_samwise_2|clf_cat_compas-two-years|{}"
DRAWN = {
    "CentralizedSync": {
        "learning_rate": 0.000117,
        "batch_size": 2048,
    },
    "CentralizedAsync": {
        "learning_rate": 0.002524,
        "batch_size": 256,
    },
    "DecentralizedSync": {
        "learning_rate": 0.002232,
        "batch_size": 256,
        "local_epochs": 8,
    },
    "DecentralizedAsync": {
        "learning_rate": 0.000632,
        "batch_size": 512,
        "local_epochs": 2,
    },
}


FIXED = {
    "patience": 20,
    "delta": 0.01,
    "epochs": 200,
    "early_stop_on": "loss",
    "min_epochs": 10,
}


@pytest.mark.parametrize("algo", sorted(DRAWN))
def test_sample_adds_fixed_patience_and_delta_without_changing_the_draws(algo):
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
        "--learning_rate 0.002232 --batch_size 256 --patience 20 --delta 0.01"
        " --local_epochs 8 --epochs 200"
        " --early_stop_on loss --min_epochs 10"
    )
    assert json.loads(out.read_text()) == {**DRAWN["DecentralizedSync"], **FIXED}


def _reference_draw_sequence(algo, key):
    rng = random.Random(seed_from_key(key))
    learning_rate = round(10 ** rng.uniform(-4, -2), 6)
    batch_size = rng.choice([256, 512, 1024, 2048])
    rng.randint(3, 10)
    rng.uniform(math.log10(1e-3), math.log10(5e-2))
    params = {"learning_rate": learning_rate, "batch_size": batch_size}
    if algo in {"DecentralizedSync", "DecentralizedAsync"}:
        params["local_epochs"] = rng.randint(1, 10)
    return params


def test_swept_values_follow_the_reference_draw_sequence():
    for algo in sorted(DRAWN):
        for i in range(500):
            key = f"key-{i}|ds|{algo}"
            params = sample(algo, key)
            for name, value in _reference_draw_sequence(algo, key).items():
                assert params[name] == value


@pytest.mark.parametrize(
    ("algo", "expected"),
    [
        (
            "CentralizedSync",
            [
                "learning_rate",
                "batch_size",
                "patience",
                "delta",
                "epochs",
                "early_stop_on",
                "min_epochs",
            ],
        ),
        (
            "CentralizedAsync",
            [
                "learning_rate",
                "batch_size",
                "patience",
                "delta",
                "epochs",
                "early_stop_on",
                "min_epochs",
            ],
        ),
        (
            "DecentralizedSync",
            [
                "learning_rate",
                "batch_size",
                "patience",
                "delta",
                "local_epochs",
                "epochs",
                "early_stop_on",
                "min_epochs",
            ],
        ),
        (
            "DecentralizedAsync",
            [
                "learning_rate",
                "batch_size",
                "patience",
                "delta",
                "local_epochs",
                "epochs",
                "early_stop_on",
                "min_epochs",
            ],
        ),
    ],
)
def test_key_order_is_unchanged(algo, expected):
    assert list(sample(algo, KEY.format(algo))) == expected
