import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import flexfl.builtins.FederatedABC as federated_module
from flexfl.builtins.FederatedABC import FederatedABC
from flexfl.builtins.Logger import Logger


class _Federated(FederatedABC):
    def setup(self):
        pass

    def master_loop(self):
        pass

    def get_worker_info(self):
        return {}


@pytest.fixture
def build_master(monkeypatch, tmp_path):
    monkeypatch.setattr(federated_module, "RESULTS_FOLDER", str(tmp_path / "results"))
    monkeypatch.setattr(
        federated_module,
        "METRICS",
        {"classification": ["mcc", "acc", "f1"], "regression": ["mape", "mse", "mae"]},
    )
    monkeypatch.setattr(Logger, "setup", lambda *args: None)
    monkeypatch.setattr(Logger, "end", lambda: None)
    monkeypatch.setattr(_Federated, "setup_failure", lambda self: None)

    def build(*, node_id=0, classification=False, standardized=False, save_model=True):
        target = {"mean": 100.0, "scale": 10.0, "standardized": standardized}
        dataset = SimpleNamespace(
            name="synthetic",
            is_classification=classification,
            base_path=str(tmp_path / "data"),
            default_folder=str(tmp_path / "data" / "_data"),
            data_path=str(tmp_path / "data" / "_data"),
            target_stats=Mock(return_value=target),
        )
        ml = SimpleNamespace(dataset=dataset, set_weights=Mock(), save_model=Mock())
        connection = SimpleNamespace(id=node_id, start_time=datetime(2026, 10, 5))
        connection.close = Mock()
        f = _Federated(
            ml=ml,
            wm=SimpleNamespace(c=connection),
            all_args={},
            base_dir=f"node_{node_id}_{classification}_{save_model}",
            save_model=save_model,
        )
        return f, target

    return build


def test_regression_master_loads_node_target_statistics(build_master):
    f, target = build_master()
    assert f.target_stats == target
    f.ml.dataset.target_stats.assert_called_once_with()
    assert f.ml.dataset.data_path == f"{f.ml.dataset.base_path}/node_0"


def test_worker_does_not_load_target_statistics(build_master):
    f, _ = build_master(node_id=1)
    f.ml.dataset.target_stats.assert_not_called()
    assert f.is_master is False


def test_master_refuses_standardized_validation_targets(build_master):
    with pytest.raises(ValueError, match="must validate on node_0"):
        build_master(standardized=True)


def test_end_writes_target_statistics_beside_model(build_master):
    f, target = build_master()
    f.target_stats = target
    f.best_weights = [1.0, 2.0]
    f.end()
    path = Path(f.base_path) / "model_target_scaling.json"
    assert path.is_file()
    assert json.loads(path.read_text()) == target
    f.ml.set_weights.assert_called_once_with([1.0, 2.0])
    f.ml.save_model.assert_called_once_with(f"{f.base_path}/model")
    f.wm.c.close.assert_called_once_with()


@pytest.mark.parametrize("classification, save_model", ((True, True), (False, False)))
def test_end_omits_target_statistics_when_not_saving_regression(
    build_master, classification, save_model
):
    f, target = build_master(classification=classification, save_model=save_model)
    f.target_stats = None if classification else target
    f.best_weights = [3.0]
    f.end()
    assert not (Path(f.base_path) / "model_target_scaling.json").exists()
    if save_model:
        f.ml.save_model.assert_called_once_with(f"{f.base_path}/model")
    else:
        f.ml.save_model.assert_not_called()
