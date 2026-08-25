import json
from pathlib import Path

import pytest

from extract_meta_features import architecture_features, extract, meta_features


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_meta_features_maps_type_to_task_and_is_classification():
    result = meta_features({"type": "classification", "input_shape": [4], "samples": 10, "output_size": 2})
    assert result["task"] == "classification"
    assert result["is_classification"] is True

    result = meta_features({"type": "regression", "input_shape": [4], "samples": 10, "output_size": 1})
    assert result["task"] == "regression"
    assert result["is_classification"] is False


def test_meta_features_n_features_is_product_of_input_shape():
    result = meta_features({"type": "classification", "input_shape": [3, 4], "samples": 10, "output_size": 2})
    assert result["n_features"] == 12


def test_meta_features_absent_input_shape_is_none():
    result = meta_features({"type": "classification", "samples": 10, "output_size": 2})
    assert result["n_features"] is None


def test_architecture_features_computes_total_parameters_and_shape():
    config = {"n_layers": 2, "n_units_l0": 8, "n_units_l1": 4, "weight_decay": 0.001}

    result = architecture_features(config, n_features=3, n_classes=2)

    assert result["total_parameters"] == 78
    assert result["n_layers"] == 2
    assert result["mean_layer_width"] == 6.0
    assert result["max_layer_width"] == 8
    assert result["weight_decay"] == 0.001


def test_architecture_features_four_layer_config_totals_4765():
    config = {
        "n_layers": 4, "n_units_l0": 78, "n_units_l1": 19, "n_units_l2": 53, "n_units_l3": 24,
        "weight_decay": 3.2627538208951424e-06,
    }
    meta = {"type": "classification", "input_shape": [10], "samples": 566602, "output_size": 2}
    mf = meta_features(meta)

    result = architecture_features(config, mf["n_features"], mf["n_classes"])

    assert result["total_parameters"] == 4765


def test_extract_single_data_name(tmp_path):
    write_json(tmp_path / "ds_a.json", {
        "name": "ds_a", "type": "classification", "input_shape": [4], "samples": 10, "output_size": 2,
    })

    result = extract(tmp_path, data_name="ds_a")

    assert set(result.keys()) == {"ds_a"}
    assert result["ds_a"]["task"] == "classification"


def test_extract_globs_directory_when_no_data_name(tmp_path):
    write_json(tmp_path / "ds_a.json", {
        "name": "ds_a", "type": "classification", "input_shape": [4], "samples": 10, "output_size": 2,
    })
    write_json(tmp_path / "ds_b.json", {
        "name": "ds_b", "type": "regression", "input_shape": [2], "samples": 20, "output_size": 1,
    })

    result = extract(tmp_path)

    assert set(result.keys()) == {"ds_a", "ds_b"}


def test_extract_raises_file_not_found_on_missing_name(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract(tmp_path, data_name="does_not_exist")
