import queue
from datetime import datetime
import pickle
import paho.mqtt.client as mqtt
from uuid import uuid4

from flexfl.builtins.CommABC import CommABC
from flexfl.builtins.Logger import Logger

TOPIC = "fl"
DISCOVER = "fl_discover"
LIVELINESS = "fl_liveliness"
QOS = 1
TIMEOUT = 3

class MQTT(CommABC):
    """
    MQTT-based communication backend.

    A graceful `close()` relies on the QoS-1 LEAVE publish being acknowledged
    (waited on with `wait_for_publish(timeout=TIMEOUT)`) before the client
    disconnects. A non-graceful crash does not run `close()`, so peers rely
    instead on the broker's Last Will and Testament (LWT) message set on
    `LIVELINESS` in `discover()`. `recv` has no timeout, so a data message
    dropped on an unreliable link can still block indefinitely; QoS 1
    mitigates but does not eliminate this.
    """

    def __init__(self, *, 
        ip: str = "localhost",
        mqtt_port: int = 1883,
        is_anchor: bool = False,
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.ip = ip
        self.port = mqtt_port
        self.is_anchor = is_anchor
        self._id = None
        self._uuid = str(uuid4())
        self._nodes = {0}
        self._start_time = datetime.now()
        self.total_nodes = 0
        self.q = queue.Queue()
        self.id_mapping = {}
        self.uuid_mapping = {}
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, 
            reconnect_on_failure=False,
            transport="tcp",
            clean_session=True,
            client_id=self._uuid,
        )
        self.discover()


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
        assert node_id in self.nodes, f"Node {node_id} not found"
        Logger.log(Logger.SEND, sender=self.id, receiver=node_id, payload_size=len(data))
        data = self.id.to_bytes(4, "big") + data
        self.client.publish(f"{TOPIC}/{self.id_mapping[node_id]}", data, qos=QOS)


    def recv(self, node_id: int = None) -> tuple[int, bytes]:
        assert node_id is None, "Support for specific node_id not implemented"
        node_id, data = self.q.get()
        return node_id, data
    

    def close(self) -> None:
        info = self.client.publish(LIVELINESS, pickle.dumps(self._uuid), qos=QOS)
        info.wait_for_publish(timeout=TIMEOUT)
        self.client.loop_stop()
        self.client.disconnect()


    def discover(self):
        self.client.on_message = self.on_message
        self.client.will_set(LIVELINESS, pickle.dumps(self._uuid), qos=QOS)
        self.client.connect(self.ip, self.port)
        self.client.subscribe(f"{TOPIC}/{self._uuid}")
        self.client.loop_start()
        if self.is_anchor:
            self._id = 0
            self.client.subscribe(DISCOVER)
            self.client.subscribe(LIVELINESS)
        else:
            self.client.publish(DISCOVER, pickle.dumps(self._uuid), qos=QOS)
            _, (_, node_uuid, self._start_time) = self.q.get()
            self.id_mapping[0] = node_uuid
            self.uuid_mapping[node_uuid] = 0
        self.id_mapping[self.id] = self._uuid
        self.uuid_mapping[self._uuid] = self.id



    def handle_discover(self, payload: bytes):
        node_uuid = pickle.loads(payload)
        self.total_nodes += 1
        Logger.log(Logger.JOIN, node_id=self.total_nodes)
        self._nodes.add(self.total_nodes)
        self.id_mapping[self.total_nodes] = node_uuid
        self.uuid_mapping[node_uuid] = self.total_nodes
        new_payload = (self.total_nodes, self._uuid, self.start_time)
        self.client.publish(f"{TOPIC}/{node_uuid}", pickle.dumps(new_payload), qos=QOS)


    def handle_liveliness(self, payload: bytes):
        node_uuid = pickle.loads(payload)
        node_id = self.uuid_mapping[node_uuid]
        Logger.log(Logger.LEAVE, node_id=node_id)
        self._nodes.remove(node_id)
        self.id_mapping.pop(node_id)
        self.uuid_mapping.pop(node_uuid)
        self.q.put((node_id, None))


    def on_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
        payload = msg.payload
        if self.id is None:
            data = pickle.loads(payload)
            self._id = data[0]
            self.q.put((0, data))
        elif msg.topic == DISCOVER:
            self.handle_discover(payload)
        elif msg.topic == LIVELINESS:
            self.handle_liveliness(payload)
        else:
            node_id = int.from_bytes(payload[:4])
            if node_id not in self.nodes:
                raise ValueError(f"Received message from unknown node {node_id}")
            data = payload[4:]
            Logger.log(Logger.RECV, sender=node_id, receiver=self.id, payload_size=len(data))
            self.q.put((node_id, data))
