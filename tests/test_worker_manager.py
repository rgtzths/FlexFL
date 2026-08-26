import queue
import signal
from datetime import datetime

import pytest

from flexfl.builtins.CommABC import CommABC
from flexfl.builtins.WorkerManager import JOIN_TYPE, WorkerManager
from flexfl.msg_layers.Raw import Raw


class _FakeComm(CommABC):
    """
    Queue-backed comm double. recv() blocks on an empty queue exactly like the
    real Zenoh/Kafka/MQTT backends, so a barrier with no arriving workers blocks
    inside recv() rather than spinning.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._id = 0
        self._nodes = {0}
        self._start_time = datetime.now()
        self.q = queue.Queue()
        self.sent = []

    @property
    def id(self) -> int:
        return self._id

    @property
    def nodes(self) -> set[int]:
        return self._nodes

    @property
    def start_time(self) -> datetime:
        return self._start_time

    def send(self, node_id: int, data: bytes) -> None:
        self.sent.append((node_id, data))

    def recv(self, node_id: int = None) -> tuple[int, bytes]:
        return self.q.get()

    def close(self) -> None:
        return

    def queue_join(self, node_id: int, info: dict = None) -> None:
        self._nodes.add(node_id)
        payload = Raw().encode({"type": JOIN_TYPE, "data": info or {"n_batches": 1}})
        self.q.put((node_id, payload))


def _wm(**kwargs) -> WorkerManager:
    return WorkerManager(c=_FakeComm(), m=Raw(), **kwargs)


def test_wait_for_workers_returns_when_pool_complete():
    wm = _wm(join_timeout=5)
    for node_id in (1, 2, 3):
        wm.c.queue_join(node_id)

    wm.wait_for_workers(3)

    assert sorted(wm.worker_info) == [1, 2, 3]


def test_wait_for_workers_join_timeout_exits_non_zero():
    wm = _wm(join_timeout=1)
    wm.c.queue_join(1)

    with pytest.raises(SystemExit) as excinfo:
        wm.wait_for_workers(3)

    assert excinfo.value.code != 0
    assert len(wm.worker_info) == 1


def test_wait_for_workers_reports_joined_and_expected_on_timeout():
    wm = _wm(join_timeout=1)
    wm.c.queue_join(1)
    wm.c.queue_join(2)

    with pytest.raises(SystemExit) as excinfo:
        wm.wait_for_workers(5)

    message = str(excinfo.value)
    assert "2" in message and "5" in message


def test_wait_for_workers_full_pool_does_not_arm_alarm(monkeypatch):
    wm = _wm(join_timeout=1)
    wm.worker_info = {1: {}, 2: {}}
    armed = []
    monkeypatch.setattr(signal, "alarm", lambda seconds: armed.append(seconds) or 0)

    wm.wait_for_workers(2)

    assert armed == []


def test_wait_for_workers_zero_timeout_is_unbounded(monkeypatch):
    wm = _wm(join_timeout=0)
    wm.c.queue_join(1)
    wm.c.queue_join(2)
    armed = []
    monkeypatch.setattr(signal, "alarm", lambda seconds: armed.append(seconds) or 0)

    wm.wait_for_workers(2)

    assert armed == []
    assert sorted(wm.worker_info) == [1, 2]


def test_wait_for_workers_restores_previous_sigalrm_handler():
    sentinel = signal.getsignal(signal.SIGALRM)
    wm = _wm(join_timeout=5)
    for node_id in (1, 2):
        wm.c.queue_join(node_id)

    wm.wait_for_workers(2)

    assert signal.getsignal(signal.SIGALRM) is sentinel


def test_wait_for_workers_explicit_timeout_overrides_default():
    wm = _wm(join_timeout=600)
    wm.c.queue_join(1)

    with pytest.raises(SystemExit):
        wm.wait_for_workers(2, timeout=1)
