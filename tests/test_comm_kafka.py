import queue
import time

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


def test_handle_disconect_removes_node_and_unblocks_recv():
    # A dead worker must be removed from all state and (node_id, None) enqueued
    # so a blocked recv() unblocks with the death sentinel.
    inst = Kafka.__new__(Kafka)
    inst._nodes = {0, 1}
    inst.id_mapping = {1: "worker-uuid"}
    inst.hearbeats = {1: 123.0}
    inst.admin = Mock()
    inst.q = queue.Queue()

    with patch("flexfl.comms.Kafka.Logger"):
        inst.handle_disconect(1)

    assert 1 not in inst._nodes
    inst.admin.delete_topics.assert_called_once_with(["fl_worker-uuid"])
    assert 1 not in inst.id_mapping
    assert 1 not in inst.hearbeats
    assert inst.q.get_nowait() == (1, None)


def test_check_liveliness_disconnects_stale_node():
    # A heartbeat older than TIMEOUT triggers handle_disconect for that node,
    # while a node with a fresh heartbeat is left connected.
    inst = Kafka.__new__(Kafka)
    inst._nodes = {0, 1, 2}
    inst.hearbeats = {1: time.time() - 100, 2: time.time()}
    inst.handle_disconect = Mock()

    inst.check_liveliness()

    inst.handle_disconect.assert_called_once_with(1)
