import pytest

pytest.importorskip("kafka")

from flexfl.comms.Kafka import Kafka


def test_clear_scopes_to_owned():
    names = [
        "fl_discover",
        "fl_heartbeat",
        "fl_abc123",
        "orders",
        "flights",
        "__consumer_offsets",
    ]
    assert sorted(Kafka._owned(names)) == sorted(
        ["fl_discover", "fl_heartbeat", "fl_abc123"]
    )


def test_clear_scopes_to_owned_empty():
    assert Kafka._owned([]) == []
