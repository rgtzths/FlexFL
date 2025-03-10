import queue
import pickle
import time
import threading
from datetime import datetime
from uuid import uuid4
from kafka import KafkaProducer, KafkaConsumer
from kafka.admin import KafkaAdminClient

from my_builtins.CommABC import CommABC

TOPIC = "fl"
DISCOVER = "fl_discover"
LIVENESS = "fl_liveness"
TIMEOUT = 2
HEARTBEAT = 0.5

class Kafka(CommABC):

    def __init__(self, *, 
        kafka_ip: str = "localhost",
        kafka_port: int = 9092,
        is_anchor: bool = False,
        **kwargs
    ) -> None:
        self.kafka_broker = f"{kafka_ip}:{kafka_port}"
        self._id = None
        self.is_anchor = is_anchor
        self._uuid = str(uuid4())
        self._nodes = set()
        self._start_time = datetime.now()
        self.q = queue.Queue()
        self.total_nodes = 0
        self.id_mapping = {}
        self.hearbeats = {}
        self.running = True
        self.thread: threading.Thread = None
        self.admin = None
        if self.is_anchor:
            self.clear()
        self.producer: KafkaProducer = None
        self.consumer: KafkaConsumer = None
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
        data = self.id.to_bytes(4) + data
        self.producer.send(
            topic=f"{TOPIC}_{self.id_mapping[node_id]}", 
            value=data, 
        )
        self.producer.flush()

    
    def recv(self, node_id: int = None) -> tuple[int, bytes]:
        assert node_id is None, "Support for specific node_id not implemented"
        return self.q.get()
    

    def close(self) -> None:
        self.running = False
        self.thread.join()
        self.producer.close()
        self.consumer.close()
        if self.id == 0:
            self.admin.close()


    def clear(self):
        self.admin = KafkaAdminClient(bootstrap_servers=self.kafka_broker)
        topics = self.admin.list_topics()
        topics = [topic for topic in topics if not topic.startswith("__")]
        self.admin.delete_topics(topics)


    def discover(self):
        self.producer = KafkaProducer(
            bootstrap_servers=self.kafka_broker,
        )
        self.consumer = KafkaConsumer(
            group_id=f"{TOPIC}_{self._uuid}",
            bootstrap_servers=self.kafka_broker,
            auto_offset_reset="earliest",
        )
        if self.is_anchor:
            self._id = 0
            self._nodes.add(0)
            self.consumer.subscribe([f"{TOPIC}_{self._uuid}", DISCOVER, LIVENESS])
        else:
            self.consumer.subscribe([f"{TOPIC}_{self._uuid}"])
            self.producer.send(DISCOVER, pickle.dumps(self._uuid))
            self.producer.flush()
            res = self.consumer.poll(timeout_ms=10000, max_records=1)
            if len(res) == 0:
                raise Exception("No response from anchor node")
            msg = res.popitem()[1][0].value
            self._id, node_uuid, self._start_time = pickle.loads(msg)
            self.id_mapping[0] = node_uuid
        self.id_mapping[self.id] = self._uuid
        self.thread = threading.Thread(target=self.listen)
        self.thread.start()


    def listen(self):
        last_time = time.time()
        while self.running:
            self.handle_msg()
            if self.is_anchor:
                if (time.time() - last_time) >= TIMEOUT:
                    last_time = time.time()
                    self.handle_liveliness()
            elif (time.time() - last_time) >= HEARTBEAT:
                last_time = time.time()
                self.producer.send(LIVENESS, self.id.to_bytes(4))
                self.producer.flush()


    def handle_msg(self):
        res = self.consumer.poll(timeout_ms=HEARTBEAT*1000)
        for topic, msgs in res.items():
            for msg in msgs:
                if topic.topic == DISCOVER:
                    self.handle_discover(msg.value)
                elif topic.topic == LIVENESS:
                    node_id = int.from_bytes(msg.value)
                    self.hearbeats[node_id] = time.time()
                else:
                    self.handle_recv(msg.value)


    def handle_discover(self, payload: bytes):
        node_uuid = pickle.loads(payload)
        self.total_nodes += 1
        self._nodes.add(self.total_nodes)
        self.id_mapping[self.total_nodes] = node_uuid
        new_payload = (self.total_nodes, self._uuid, self.start_time)
        self.producer.send(f"{TOPIC}_{node_uuid}", pickle.dumps(new_payload))
        self.producer.flush()


    def handle_liveliness(self):
        for node_id, timestamp in list(self.hearbeats.items()):
            if (time.time() - timestamp) > TIMEOUT:
                self.admin.delete_topics([f"{TOPIC}_{self.id_mapping[node_id]}"])
                self._nodes.remove(node_id)
                self.id_mapping.pop(node_id)
                self.hearbeats.pop(node_id)
                self.q.put((node_id, None))


    def handle_recv(self, payload: bytes):
        node_id = int.from_bytes(payload[:4])
        data = payload[4:]
        self.q.put((node_id, data))

            
        