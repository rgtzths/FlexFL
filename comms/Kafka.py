import queue
import pickle
import time
import threading
from datetime import datetime
from kafka import KafkaProducer, KafkaConsumer
from kafka.admin import KafkaAdminClient
from uuid import uuid4
from typing import Any, Generator

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
        super().__init__(**kwargs)
        self.kafka_broker = f"{kafka_ip}:{kafka_port}"
        self._id = None
        self.is_anchor = is_anchor
        self._uuid = uuid4()
        self._nodes = set()
        self._start_time = datetime.now()
        self.q = queue.Queue()
        self.total_nodes = 0
        self.id_mapping = {}
        self.hearbeats = {}
        self.running = True
        self.threads: list[threading.Thread] = []
        self.admin: KafkaAdminClient = None
        if self.is_anchor:
            self.clear()
        self.producer: KafkaProducer = None
        self.consumer: KafkaConsumer = None
        self.discover_sub: KafkaConsumer = None
        self.live_sub: KafkaConsumer = None
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
        self.producer.send(f"{TOPIC}_{self.id_mapping[node_id]}", data)
        self.producer.flush()


    def recv(self, node_id: int = None) -> tuple[int, bytes]:
        assert node_id is None, "Support for specific node_id not implemented"
        return self.q.get()
    

    def close(self) -> None:
        self.running = False
        self.producer.close()
        self.consumer.close()
        for thread in self.threads:
            thread.join()
        if self.id == 0:
            self.discover_sub.close()
            self.live_sub.close()
            topics = self.admin.list_topics()
            topics = [topic for topic in topics if topic.startswith(TOPIC)]
            self.admin.delete_topics(topics)
            self.admin.close()


    def clear(self):
        self.admin = KafkaAdminClient(bootstrap_servers=self.kafka_broker)
        topics = self.admin.list_topics()
        topics = [topic for topic in topics if not topic.startswith("__")]
        self.admin.delete_topics(topics)


    def get_msgs(self, res: dict[Any, list]) -> Generator:
        if len(res) == 0:
            return
        for _, messages in res.items():
            for msg in messages:
                yield msg


    def discover(self):
        self.producer = KafkaProducer(bootstrap_servers=self.kafka_broker)
        self.consumer = KafkaConsumer(
            f"{TOPIC}_{self._uuid}",
            group_id=f"fl_{self._uuid}",
            bootstrap_servers=self.kafka_broker,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )
        if self.is_anchor:
            self._id = 0
            self._nodes.add(0)
            self.threads.append(threading.Thread(target=self.handle_discover))
            self.threads.append(threading.Thread(target=self.handle_liveliness))
        else:
            self.producer.send(DISCOVER, pickle.dumps(self._uuid))
            self.producer.flush()
            res = self.consumer.poll(timeout_ms=10000, max_records=1)
            if len(res) == 0:
                print("No anchor found")
                self.close()
                exit(1)
            for msg in self.get_msgs(res):
                self._id, uuid, self._start_time = pickle.loads(msg.value)
                self.id_mapping[0] = uuid
            self.threads.append(threading.Thread(target=self.send_heartbeat))
        self.id_mapping[self.id] = self._uuid
        self.threads.append(threading.Thread(target=self.handle_recv))
        for thread in self.threads:
            thread.start()
                    

    def handle_discover(self):
        self.discover_sub = KafkaConsumer(
            DISCOVER,
            group_id=DISCOVER,
            bootstrap_servers=self.kafka_broker,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )
        while self.running:
            for msg in self.get_msgs(self.discover_sub.poll(timeout_ms=1000)):
                uuid = pickle.loads(msg.value)
                if uuid == self._uuid:
                    continue
                self.total_nodes += 1
                self._nodes.add(self.total_nodes)
                self.id_mapping[self.total_nodes] = uuid
                payload = (self.total_nodes, self._uuid, self.start_time)
                self.producer.send(f"{TOPIC}_{uuid}", pickle.dumps(payload))
                self.producer.flush()


    def handle_liveliness(self):
        self.live_sub = KafkaConsumer(
            LIVENESS,
            group_id=LIVENESS,
            bootstrap_servers=self.kafka_broker,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )
        while self.running:
            for msg in self.get_msgs(self.live_sub.poll(timeout_ms=1000)):
                node_id = int.from_bytes(msg.value)
                self.hearbeats[node_id] = datetime.now()
            for node_id, timestamp in list(self.hearbeats.items()):
                if (datetime.now() - timestamp).total_seconds() > TIMEOUT:
                    self.admin.delete_topics([f"{TOPIC}_{self.id_mapping[node_id]}"])
                    self._nodes.remove(node_id)
                    self.id_mapping.pop(node_id)
                    self.hearbeats.pop(node_id)
                    self.q.put((node_id, None))


    def send_heartbeat(self):
        while self.running:
            self.producer.send(LIVENESS, self.id.to_bytes(4))
            self.producer.flush()
            time.sleep(HEARTBEAT)


    def handle_recv(self):
        while self.running:
            for msg in self.get_msgs(self.consumer.poll(timeout_ms=1000)):
                data = msg.value
                node_id = int.from_bytes(data[:4])
                data = data[4:]
                self.q.put((node_id, data))
