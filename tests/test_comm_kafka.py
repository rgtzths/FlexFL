import pytest

pytest.importorskip("kafka")

from unittest.mock import Mock, patch

from flexfl.comms.Kafka import Kafka


def test_send_does_not_flush():
    # Data sends are batched (delivered on linger/batch/close); send() must
    # enqueue via producer.send without a synchronous per-message flush.
    inst = Kafka.__new__(Kafka)
    inst._id = 0
    inst._nodes = {0, 1}
    inst.id_mapping = {1: "worker-uuid"}
    producer = Mock()
    inst.producer = producer

    with patch("flexfl.comms.Kafka.Logger"):
        inst.send(1, b"payload")

    producer.send.assert_called_once()
    producer.flush.assert_not_called()


def test_clear_deletes_only_owned():
    # clear() must scope its deletions to backend-owned topics/groups, leaving
    # foreign ones untouched.
    inst = Kafka.__new__(Kafka)
    inst.kafka_broker = "localhost:9092"
    admin = Mock()
    admin.list_topics.return_value = ["fl_discover", "fl_abc123", "orders"]
    admin.list_consumer_groups.return_value = [
        ("fl_heartbeat", ""),
        ("other_group", ""),
    ]

    with patch("flexfl.comms.Kafka.KafkaAdminClient", return_value=admin):
        inst.clear()

    admin.delete_topics.assert_called_once_with(["fl_discover", "fl_abc123"])
    admin.delete_consumer_groups.assert_called_once_with(["fl_heartbeat"])


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
