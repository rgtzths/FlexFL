import queue
from datetime import datetime
import pickle
import paho.mqtt.client as mqtt
from uuid import uuid4

from my_builtins.CommABC import CommABC

TOPIC = "fl"
DISCOVER = "fl_discover"
LIVELINESS = "fl_liveliness"
TIMEOUT = 2
HEARTBEAT = 0.5
QOS = 0

class MQTT(CommABC):
    
    def __init__(self, *, 
        mqtt_ip: str = "localhost",
        mqtt_port: int = 1883,
        is_anchor: bool = False,
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.ip = mqtt_ip
        self.port = mqtt_port
        self.is_anchor = is_anchor
        self._id = None
        self._uuid = str(uuid4())
        self._nodes = set()
        self._start_time = datetime.now()
        self.total_nodes = 0
        self.q = queue.Queue()
        self.id_mapping = {}
        self.uuid_mapping = {}
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, 
            reconnect_on_failure=False,
            transport="tcp"
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
        data = self.id.to_bytes(4, "big") + data
        self.client.publish(f"{TOPIC}/{self.id_mapping[node_id]}", data, qos=QOS)


    def recv(self, node_id: int = None) -> tuple[int, bytes]:
        assert node_id is None, "Support for specific node_id not implemented"
        return self.q.get()
    

    def close(self) -> None:
        self.client.publish(LIVELINESS, pickle.dumps(self._uuid), qos=QOS)
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
            self._nodes.add(0)
            self.client.subscribe(DISCOVER)
            self.client.subscribe(LIVELINESS)
        else:
            self.client.publish(DISCOVER, pickle.dumps(self._uuid), qos=QOS)
            _, msg = self.q.get()
            self._id, node_uuid, self._start_time = pickle.loads(msg)
            self.id_mapping[0] = node_uuid
            self.uuid_mapping[node_uuid] = 0
        self.id_mapping[self.id] = self._uuid
        self.uuid_mapping[self._uuid] = self.id


    def handle_discover(self, payload: bytes):
        node_uuid = pickle.loads(payload)
        self.total_nodes += 1
        self._nodes.add(self.total_nodes)
        self.id_mapping[self.total_nodes] = node_uuid
        self.uuid_mapping[node_uuid] = self.total_nodes
        new_payload = (self.total_nodes, self._uuid, self.start_time)
        self.send(self.total_nodes, pickle.dumps(new_payload))


    def handle_liveliness(self, payload: bytes):
        node_uuid = pickle.loads(payload)
        node_id = self.uuid_mapping[node_uuid]
        self._nodes.remove(node_id)
        self.id_mapping.pop(node_id)
        self.uuid_mapping.pop(node_uuid)
        self.q.put((node_id, None))


    def on_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
        payload = msg.payload
        if msg.topic == DISCOVER:
            self.handle_discover(payload)
        elif msg.topic == LIVELINESS:
            self.handle_liveliness(payload)
        else:
            node_id = int.from_bytes(payload[:4])
            data = payload[4:]
            self.q.put((node_id, data))
        

            