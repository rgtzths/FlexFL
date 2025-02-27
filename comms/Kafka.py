import queue
import pickle
import time
import threading
from datetime import datetime
from kafka import KafkaProducer, KafkaConsumer
from kafka.admin import KafkaAdminClient
from uuid import uuid4
import argparse

from my_builtins.CommABC import CommABC

TOPIC = "fl"
DISCOVER = "fl_discover"
LIVENESS = "fl_liveness"
TIMEOUT = 2

class Kafka(CommABC):
    
    def __init__(self, *, 
        ip: str = "localhost",
        port: int = 9092,
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.kafka_broker = f"{ip}:{port}"
        self._id = None
        self._uuid = uuid4()
        self._nodes = set()
        self._start_time = datetime.now()
        self.q = queue.Queue()
        self.total_nodes = 0
        self.producer = KafkaProducer(bootstrap_servers=self.kafka_broker)
        self.consumer = KafkaConsumer(
            f"{TOPIC}_{self._uuid}",
            group_id=f"fl_{self._uuid}",
            bootstrap_servers=self.kafka_broker,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )
        self.discover_sub = None
        self.live_sub = None
        self.admin = None
        self.id_mapping = {}
        self.hearbeats = {}
        self.threads: list[threading.Thread] = []
        self.running = True
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


    def get_msgs(self, res):
        if len(res) == 0:
            return
        for _, messages in res.items():
            for msg in messages:
                yield msg


    def discover(self):
        self.producer.send(DISCOVER, pickle.dumps(self._uuid))
        self.producer.flush()
        res = self.consumer.poll(timeout_ms=5000, max_records=1)
        if len(res) == 0:
            self._id = 0
            self.admin = KafkaAdminClient(bootstrap_servers=self.kafka_broker)
            self.threads.append(threading.Thread(target=self.handle_discover))
            self.threads.append(threading.Thread(target=self.handle_liveliness))
        else:
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
            for msg in self.get_msgs(self.discover_sub.poll(timeout_ms=500)):
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
            for msg in self.get_msgs(self.live_sub.poll(timeout_ms=500)):
                node_id= int.from_bytes(msg.value, "big")
                timestamp = datetime.now()
                if node_id not in self.hearbeats:
                    self.hearbeats[node_id] = timestamp
                else:
                    self.hearbeats[node_id] = max(self.hearbeats[node_id], timestamp)
            for node_id, timestamp in list(self.hearbeats.items()):
                if (datetime.now() - timestamp).total_seconds() > TIMEOUT:
                    self.admin.delete_topics([f"{TOPIC}_{self.id_mapping[node_id]}"])
                    self._nodes.remove(node_id)
                    self.id_mapping.pop(node_id)
                    self.hearbeats.pop(node_id)
                    self.q.put((node_id, None))


    def send_heartbeat(self):
        while self.running:
            self.producer.send(f"{LIVENESS}", self.id.to_bytes(4, "big"))
            self.producer.flush()
            time.sleep(0.5)


    def handle_recv(self):
        while self.running:
            for msg in self.get_msgs(self.consumer.poll(timeout_ms=500)):
                data = msg.value
                node_id = int.from_bytes(data[:4], "big")
                data = data[4:]
                self.q.put((node_id, data))


    @staticmethod
    def delete_all_topics(ip: str = "localhost", port: int = 9092):
        kafka_broker = f"{ip}:{port}"
        admin = KafkaAdminClient(bootstrap_servers=kafka_broker)
        topics = admin.list_topics()
        topics = [topic for topic in topics if not topic.startswith("__")]
        print(f"Topics: {topics}")
        admin.delete_topics(topics)
        admin.close()
        print("✅ All topics deleted successfully!")
