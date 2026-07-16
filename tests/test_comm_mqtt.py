import pytest

pytest.importorskip("paho.mqtt.client")

from unittest.mock import Mock, patch

from flexfl.comms.MQTT import MQTT, LIVELINESS


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
