import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from flexfl.builtins.Logger import Logger
from flexfl.fl_algos.CentralizedAsync import CentralizedAsync
from flexfl.fl_algos.CentralizedSync import CentralizedSync
from flexfl.fl_algos.DecentralizedAsync import DecentralizedAsync
from flexfl.fl_algos.DecentralizedSync import DecentralizedSync

CAP = 200
MAX_TASKS = 2000
INFO = {1: {"n_batches": 1, "n_samples": 1}, 2: {"n_batches": 1, "n_samples": 1}}


class _WorkerManager:
    def __init__(self):
        self.worker_info = dict(INFO)
        self.tasks = 0
        self.ended = False
        self.pending = []

    def _task(self):
        self.tasks += 1
        if self.tasks > MAX_TASKS:
            raise RuntimeError(f"still sending after {MAX_TASKS} tasks")

    def wait_for_workers(self, n):
        pass

    def get_subpool(self, size, fn):
        return sorted(INFO)[:size]

    def get_info(self, worker_id):
        return INFO[worker_id]

    def send_n(self, workers, payload=None, type_=None):
        for _ in workers:
            self._task()
        self.pending = list(workers)

    def send(self, node_id, payload=None, type_=None):
        self._task()

    def recv_n(self, workers, type_=None):
        if list(workers) != self.pending:
            raise RuntimeError("recv_n for workers with no outstanding work")
        self.pending = []
        for worker_id in workers:
            yield worker_id, 1.0

    def end(self):
        self.ended = True


class _ML:
    def get_weights(self):
        return 1.0

    def set_weights(self, weights):
        pass

    def apply_gradients(self, gradients):
        pass


class _Quiet:
    def update(self, *args, **kwargs):
        pass

    def print(self, *args, **kwargs):
        pass


def _run(cls, monkeypatch, stop_after=None, epochs=CAP):
    logged = []
    monkeypatch.setattr(Logger, "log", lambda event, **kwargs: logged.append(event))
    validated = []

    def validate(epoch, split="val", verbose=False):
        validated.append(epoch)
        return {"mcc": 0.0}, 0.0, 0.0

    algo = object.__new__(cls)
    algo.wm = _WorkerManager()
    algo.ml = _ML()
    algo.min_workers = len(INFO)
    algo.epochs = epochs
    algo.running = True
    algo.rr = set()
    algo.validate = validate
    algo.early_stop = lambda: stop_after is not None and len(validated) >= stop_after
    if cls in (CentralizedSync, DecentralizedSync):
        algo.epoch_threshold = 0.5
        algo.master_loop()
    else:
        algo.iteration = 0
        algo.working = set(INFO)
        algo.penalty = 0.5
        algo.total_batches = len(INFO)
        algo.weights = 1.0
        algo.status = _Quiet()
        algo.console = _Quiet()
        while algo.running:
            algo.on_work_done(min(algo.working), 1.0)
    return algo, validated, logged


SYNC = [CentralizedSync, DecentralizedSync]
ASYNC = [CentralizedAsync, DecentralizedAsync]


@pytest.mark.parametrize("cls", SYNC + ASYNC)
def test_trains_to_the_cap_when_early_stop_never_fires(cls, monkeypatch):
    algo, validated, logged = _run(cls, monkeypatch)
    assert validated == list(range(1, CAP + 1))
    assert logged.count(Logger.END) == 1
    assert not algo.running or cls in SYNC


@pytest.mark.parametrize("cls", SYNC + ASYNC)
def test_early_stop_ends_the_run_before_the_cap(cls, monkeypatch):
    algo, validated, logged = _run(cls, monkeypatch, stop_after=3)
    assert validated == [1, 2, 3]
    assert logged.count(Logger.END) == 1


@pytest.mark.parametrize("cls", SYNC)
def test_sync_loops_send_no_round_past_the_cap(cls, monkeypatch):
    algo, validated, logged = _run(cls, monkeypatch)
    assert algo.wm.tasks == len(INFO) * CAP
    assert algo.wm.ended


@pytest.mark.parametrize("cls", SYNC)
def test_sync_loops_keep_one_overlapped_round_after_early_stop(cls, monkeypatch):
    algo, validated, logged = _run(cls, monkeypatch, stop_after=3)
    assert algo.wm.tasks == len(INFO) * 4


@pytest.mark.parametrize("cls", SYNC)
def test_sync_loops_stop_after_the_first_epoch_on_a_non_positive_cap(cls, monkeypatch):
    algo, validated, logged = _run(cls, monkeypatch, epochs=0)
    assert validated == [1]
    assert logged.count(Logger.END) == 1
    assert algo.wm.ended


@pytest.mark.parametrize("cls", ASYNC)
@pytest.mark.parametrize("stop_after, completions", [(None, len(INFO) * CAP), (3, len(INFO) * 3)])
def test_async_loops_send_no_task_after_the_stop(cls, monkeypatch, stop_after, completions):
    algo, validated, logged = _run(cls, monkeypatch, stop_after=stop_after)
    assert algo.iteration == completions
    assert algo.wm.tasks == completions - 1


@pytest.mark.parametrize("all_args, epochs", [({"fl": "cs"}, 200), ({"fl": "cs", "epochs": 7}, 7)])
def test_master_records_the_resolved_cap(tmp_path, monkeypatch, all_args, epochs):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Logger, "setup", lambda file_path: None)
    passed = dict(all_args)
    algo = object.__new__(CentralizedSync)
    algo.wm = SimpleNamespace(c=SimpleNamespace(id=0, start_time=datetime(2026, 1, 1)))
    algo.ml = SimpleNamespace(dataset=SimpleNamespace(default_folder="a", data_path="b"))
    algo.base_dir = "run"
    algo.results_folder = None
    algo.all_args = passed
    algo.epochs = epochs
    algo.setup_nodes()
    recorded = json.loads((tmp_path / "results" / "run" / "args.json").read_text())
    assert recorded == {**all_args, "epochs": epochs}
    assert passed == all_args
