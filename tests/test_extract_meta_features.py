import json
from pathlib import Path

import pytest

from extract_meta_features import extract, meta_features


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
