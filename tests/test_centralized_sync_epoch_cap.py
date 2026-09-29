from flexfl.builtins.Logger import Logger
from flexfl.fl_algos.CentralizedSync import CentralizedSync


class _WorkerManager:
    def __init__(self, n_batches, max_sends=200):
        self.n_batches = n_batches
        self.max_sends = max_sends
        self.sends = 0
        self.ended = False

    def wait_for_workers(self, n):
        pass

    def get_subpool(self, size, fn):
        return sorted(self.n_batches)[:size]

    def get_info(self, worker_id):
        return {"n_batches": self.n_batches[worker_id]}

    def send_n(self, workers, payload=None, type_=None):
        self.sends += 1
        if self.sends > self.max_sends:
            raise RuntimeError(f"master_loop still running after {self.max_sends} rounds")

    def recv_n(self, workers, type_=None):
        for worker_id in workers:
            yield worker_id, 1.0

    def end(self):
        self.ended = True


class _ML:
    def __init__(self):
        self.applied = 0

    def get_weights(self):
        return None

    def apply_gradients(self, gradients):
        self.applied += 1


def _run_master_loop(monkeypatch, n_batches, epochs, stop_after=None):
    logged = []
    monkeypatch.setattr(Logger, "log", lambda event, **kwargs: logged.append(event))
    validated = []
    algo = object.__new__(CentralizedSync)
    algo.wm = _WorkerManager(n_batches)
    algo.ml = _ML()
    algo.min_workers = len(n_batches)
    algo.epochs = epochs
    algo.epoch_threshold = 0.5
    algo.validate = lambda epoch, split="val", verbose=False: validated.append(epoch)
    algo.early_stop = lambda: stop_after is not None and len(validated) >= stop_after
    algo.master_loop()
    return algo, validated, logged


def test_stops_at_cap_when_min_workers_does_not_divide_total_batches(monkeypatch):
    n_batches = {worker_id: 7 for worker_id in range(1, 14)}
    n_batches[14] = 6
    algo, validated, logged = _run_master_loop(monkeypatch, n_batches, epochs=10)
    assert validated == list(range(1, 11))
    assert logged.count(Logger.END) == 1
    assert algo.wm.ended


def test_early_stop_ends_a_non_divisible_run_before_the_cap(monkeypatch):
    n_batches = {worker_id: 7 for worker_id in range(1, 14)}
    n_batches[14] = 6
    algo, validated, logged = _run_master_loop(monkeypatch, n_batches, epochs=10, stop_after=3)
    assert validated == [1, 2, 3]
    assert logged.count(Logger.END) == 1
    assert algo.wm.ended


def test_divisible_run_keeps_its_validation_points(monkeypatch):
    algo, validated, logged = _run_master_loop(monkeypatch, {1: 2, 2: 2}, epochs=3)
    assert validated == [1, 2, 3]
    assert (algo.wm.sends, algo.ml.applied) == (7, 6)
    assert logged.count(Logger.END) == 1
