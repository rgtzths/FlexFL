import queue
from datetime import datetime
import pickle
import paho.mqtt.client as mqtt
from uuid import uuid4
import threading
import time

from my_builtins.CommABC import CommABC

TOPIC = "fl"
DISCOVER = "fl_discover"
LIVELINESS = "fl_liveliness"
TIMEOUT = 2
HEARTBEAT = 0.5

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
        self._uuid = uuid4()
        self._nodes = set()
        self._start_time = datetime.now()
        self.total_nodes = 0
        self.q = queue.Queue()
        self.keep_alives = queue.Queue()
        self.id_mapping = {}
        self.hearbeats = {}
        self.running = True
        self.threads: list[threading.Thread] = []
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, 
            reconnect_on_failure=False
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
        data = self.id.to_bytes(4, "big") + data
        self.client.publish(f"{TOPIC}/{self.id_mapping[node_id]}", data)


    def recv(self, node_id: int = None) -> tuple[int, bytes]:
        assert node_id is None, "Support for specific node_id not implemented"
        return self.q.get()
    

    def close(self) -> None:
        self.running = False
        for thread in self.threads:
            thread.join()
        self.client.loop_stop()
        self.client.disconnect()


    def discover(self):
        self.client.on_message = self.on_message
        self.client.connect(self.ip, self.port)
        self.client.subscribe(f"{TOPIC}/{self._uuid}")
        self.client.loop_start()
        
        if self.is_anchor:
            self._id = 0
            self._nodes.add(0)
            self.client.subscribe(DISCOVER)
            self.client.subscribe(LIVELINESS)
            self.threads.append(threading.Thread(target=self.handle_liveliness))
        else:
            self.client.publish(DISCOVER, pickle.dumps(self._uuid))
            _, msg = self.q.get()
            self._id, uuid, self._start_time = pickle.loads(msg)
            self.id_mapping[0] = uuid
            self.threads.append(threading.Thread(target=self.send_hearbeat))
        self.id_mapping[self.id] = self._uuid
        for thread in self.threads:
            thread.start()


    def handle_discover(self, payload: bytes):
        uuid = pickle.loads(payload)
        self.total_nodes += 1
        self._nodes.add(self.total_nodes)
        self.id_mapping[self.total_nodes] = uuid
        new_payload = (self.total_nodes, self._uuid, self.start_time)
        self.send(self.total_nodes, pickle.dumps(new_payload))


    def on_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
        payload = msg.payload
        if msg.topic == LIVELINESS:
            self.keep_alives.put(int.from_bytes(payload))
        elif msg.topic == DISCOVER:
            self.handle_discover(payload)
        else:
            node_id = int.from_bytes(payload[:4])
            data = payload[4:]
            self.q.put((node_id, data))


    def send_hearbeat(self):
        while self.running:
            self.client.publish(LIVELINESS, self.id.to_bytes(4))
            time.sleep(HEARTBEAT)


    def handle_liveliness(self):
        while self.running:
            while not self.keep_alives.empty():
                node_id = self.keep_alives.get()
                self.hearbeats[node_id] = datetime.now()
            for node_id, timestamp in list(self.hearbeats.items()):
                if (datetime.now() - timestamp).total_seconds() > TIMEOUT:
                    self._nodes.remove(node_id)
                    self.id_mapping.pop(node_id)
                    self.hearbeats.pop(node_id)
                    self.q.put((node_id, None))
            time.sleep(1)

            