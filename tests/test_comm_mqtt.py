import pytest

pytest.importorskip("paho.mqtt.client")

import pickle

from unittest.mock import Mock, patch

from flexfl.comms.MQTT import MQTT, DISCOVER, LIVELINESS, QOS, TIMEOUT


def _make_anchor_mqtt():
    # Patch the paho Client class so construction never touches a real broker;
    # is_anchor=True avoids discover()'s blocking q.get() on the non-anchor path.
    with patch("paho.mqtt.client.Client") as mock_client_cls:
        instance = MQTT(is_anchor=True)
        return instance, mock_client_cls.return_value


def test_send_uses_qos1():
    # Drives send()'s publish call and asserts it carries qos=1 (the QOS
    # module constant consumed at call time, not hardcoded in the test).
    instance, mock_client = _make_anchor_mqtt()
    mock_client.publish.reset_mock()

    instance.send(0, b"payload")

    assert mock_client.publish.called
    _, kwargs = mock_client.publish.call_args
    assert kwargs["qos"] == 1


def test_subscriptions_use_qos1():
    # The anchor subscribes to its data topic, DISCOVER and LIVELINESS; each
    # subscription must be granted QoS 1 so the broker->subscriber hop is not
    # fire-and-forget (effective delivery QoS is min(publish, subscription)).
    instance, mock_client = _make_anchor_mqtt()

    calls = mock_client.subscribe.call_args_list
    assert len(calls) == 3
    for args, kwargs in calls:
        assert kwargs.get("qos") == QOS


def test_close_waits_for_leave_before_disconnect():
    # Drives close()'s LEAVE publish and asserts wait_for_publish is called
    # on the publish() return value, before disconnect() is called.
    instance, mock_client = _make_anchor_mqtt()

    parent = Mock()
    parent.attach_mock(mock_client.publish, "publish")
    parent.attach_mock(mock_client.publish.return_value.wait_for_publish, "wait_for_publish")
    parent.attach_mock(mock_client.loop_stop, "loop_stop")
    parent.attach_mock(mock_client.disconnect, "disconnect")

    instance.close()

    call_names = [c[0] for c in parent.mock_calls]
    assert "wait_for_publish" in call_names
    assert "disconnect" in call_names
    assert call_names.index("wait_for_publish") < call_names.index("disconnect")

    publish_call = mock_client.publish.call_args
    args, kwargs = publish_call
    assert args[0] == LIVELINESS
    assert kwargs["qos"] == 1

    mock_client.publish.return_value.wait_for_publish.assert_called_once_with(
        timeout=TIMEOUT
    )


def test_close_runs_disconnect_when_wait_for_publish_raises():
    # If wait_for_publish raises (full queue / broker gone), close() must still
    # tear the client down so the network-loop thread is not leaked.
    instance, mock_client = _make_anchor_mqtt()
    mock_client.publish.return_value.wait_for_publish.side_effect = RuntimeError(
        "no connection"
    )

    instance.close()

    mock_client.loop_stop.assert_called_once()
    mock_client.disconnect.assert_called_once()


def test_will_set_registers_lwt():
    # The Last Will and Testament on LIVELINESS is what surfaces a crashed
    # worker to the anchor; assert it is registered with the pickled uuid at QoS 1.
    instance, mock_client = _make_anchor_mqtt()

    mock_client.will_set.assert_called_once_with(
        LIVELINESS, pickle.dumps(instance._uuid), qos=QOS
    )


def test_handle_liveliness_removes_node_and_unblocks_recv():
    # A LEAVE removes the node from _nodes and enqueues (node_id, None) so a
    # blocked recv() unblocks with the death sentinel.
    instance, mock_client = _make_anchor_mqtt()
    worker_uuid = "worker-1"
    instance.uuid_mapping[worker_uuid] = 1
    instance.id_mapping[1] = worker_uuid
    instance._nodes.add(1)

    instance.handle_liveliness(pickle.dumps(worker_uuid))

    assert 1 not in instance._nodes
    assert instance.q.get_nowait() == (1, None)


def test_handle_liveliness_duplicate_leave_is_noop():
    # Under at-least-once delivery a LEAVE can be redelivered; the second call
    # must not raise and must leave state unchanged.
    instance, mock_client = _make_anchor_mqtt()
    worker_uuid = "worker-1"
    instance.uuid_mapping[worker_uuid] = 1
    instance.id_mapping[1] = worker_uuid
    instance._nodes.add(1)

    instance.handle_liveliness(pickle.dumps(worker_uuid))
    nodes_after_first = set(instance._nodes)

    instance.handle_liveliness(pickle.dumps(worker_uuid))

    assert instance._nodes == nodes_after_first
    assert 1 not in instance._nodes


def test_handle_discover_duplicate_does_not_mint_phantom():
    # A redelivered DISCOVER must reuse the existing id assignment instead of
    # incrementing total_nodes and adding a phantom node.
    instance, mock_client = _make_anchor_mqtt()
    worker_uuid = "worker-x"

    instance.handle_discover(pickle.dumps(worker_uuid))
    assert instance.total_nodes == 1
    first_id = instance.uuid_mapping[worker_uuid]

    instance.handle_discover(pickle.dumps(worker_uuid))

    assert instance.total_nodes == 1
    assert instance.uuid_mapping[worker_uuid] == first_id
    assert instance._nodes == {0, first_id}


def _data_msg(topic, payload):
    msg = Mock()
    msg.topic = topic
    msg.payload = payload
    return msg


def test_data_message_dedup_by_sequence():
    # A redelivered data message (same per-sender seq) is dropped; a strictly
    # higher seq is enqueued.
    instance, mock_client = _make_anchor_mqtt()
    instance._nodes.add(1)

    frame0 = (1).to_bytes(4, "big") + (0).to_bytes(8, "big") + b"hello"
    instance.on_message(None, None, _data_msg("fl/data", frame0))
    assert instance.q.get_nowait() == (1, b"hello")

    instance.on_message(None, None, _data_msg("fl/data", frame0))
    assert instance.q.empty()

    frame1 = (1).to_bytes(4, "big") + (1).to_bytes(8, "big") + b"world"
    instance.on_message(None, None, _data_msg("fl/data", frame1))
    assert instance.q.get_nowait() == (1, b"world")
