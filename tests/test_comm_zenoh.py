import contextlib
import socket
import time
from unittest.mock import patch

import pytest

zenoh = pytest.importorskip("zenoh")

from flexfl.comms import Zenoh as zenoh_module  # noqa: E402
from flexfl.comms.Zenoh import Zenoh  # noqa: E402

TINY_QUEUES = (
    "{control:1,real_time:1,interactive_high:1,interactive_low:1,"
    "data_high:1,data:1,data_low:1,background:1}"
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_send_blocks_instead_of_dropping():
    with patch("zenoh.open") as mock_open:
        anchor = Zenoh(is_anchor=True)
        session = mock_open.return_value
        anchor.send(0, b"payload")

    _, kwargs = session.put.call_args
    assert kwargs["congestion_control"] == zenoh.CongestionControl.BLOCK


def test_burst_to_worker_loses_no_message():
    # Without the one-slot queues and the slow receiver the burst never fills
    # the transmit queue on loopback, and this test passes on dropping code.
    # With multicast scouting on, another zenoh process on the host can answer
    # discovery and the worker joins the wrong anchor.
    real_open = zenoh.open

    def open_isolated(conf):
        conf.insert_json5("transport/link/tx/queue/size", TINY_QUEUES)
        conf.insert_json5("scouting/multicast/enabled", "false")
        return real_open(conf)

    real_handle_recv = Zenoh.handle_recv

    def slow_handle_recv(self, sample):
        time.sleep(0.005)
        real_handle_recv(self, sample)

    port = _free_port()
    with contextlib.ExitStack() as stack:
        with patch.object(zenoh_module.zenoh, "open", side_effect=open_isolated):
            anchor = Zenoh(ip="127.0.0.1", zenoh_port=port, is_anchor=True)
            stack.callback(anchor.close)
            with patch.object(Zenoh, "handle_recv", slow_handle_recv):
                worker = Zenoh(ip="127.0.0.1", zenoh_port=port)
            stack.callback(worker.close)
        time.sleep(1.0)
        n, payload = 1000, b"x" * 400_000
        for _ in range(n):
            anchor.send(worker.id, payload)
        received = 0
        deadline = time.time() + 30
        while received < n and time.time() < deadline:
            if not worker.q.empty():
                worker.q.get()
                received += 1
            else:
                time.sleep(0.01)
        assert received == n, f"worker received {received} of {n}"
