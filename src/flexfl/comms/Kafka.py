import queue
import pickle
import threading
from datetime import datetime
from uuid import uuid4
from kafka import KafkaProducer, KafkaConsumer, TopicPartition
from kafka.admin import KafkaAdminClient
import time

from flexfl.builtins.CommABC import CommABC
from flexfl.builtins.Logger import Logger

TOPIC = "fl"
DISCOVER = "fl_discover"
HEARTBEAT = "fl_heartbeat"
TIMEOUT = 3
HEARTBEAT_INTERVAL = 1

class Kafka(CommABC):

    def __init__(self, *, 
        ip: str = "localhost",
        kafka_port: int = 9092,
        is_anchor: bool = False,
        **kwargs
    ) -> None:
        self.kafka_broker = f"{ip}:{kafka_port}"
        self._id = None
        self.is_anchor = is_anchor
        self._uuid = str(uuid4())
        self._nodes = {0}
        self._start_time = datetime.now()
        self.q = queue.Queue()
        self.total_nodes = 0
        self.id_mapping = {}
        self.hearbeats = {}
        self.running = True
        self.thread = threading.Thread(target=self.listen)
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
        assert node_id in self.nodes, f"Node {node_id} not found"
        Logger.log(Logger.SEND, sender=self.id, receiver=node_id, payload_size=len(data))
        data = self.id.to_bytes(4) + data
        self.producer.send(
            topic=f"{TOPIC}_{self.id_mapping[node_id]}", 
            value=data, 
        )
        self.producer.flush()

    
    def recv(self, node_id: int = None) -> tuple[int, bytes]:
        assert node_id is None, "Support for specific node_id not implemented"
        node_id, data = self.q.get()
        return node_id, data
        
    

    def close(self) -> None:
        if not self.is_anchor:
            self.producer.send(HEARTBEAT, self.id.to_bytes(4, "big") + bytes([0]))
            self.producer.flush()
        self.running = False
        self.thread.join()
        self.producer.close()
        self.consumer.close()
        if self.is_anchor:
            self.admin.close()


    def clear(self):
        self.admin = KafkaAdminClient(bootstrap_servers=self.kafka_broker, client_id="fl_admin")
        topics = self.admin.list_topics()
        topics = [topic for topic in topics if not topic.startswith("__")]
        self.admin.delete_topics(topics)
        groups = self.admin.list_consumer_groups()
        groups = [g[0] for g in groups]
        self.admin.delete_consumer_groups(groups)


    def discover(self):
        self.producer = KafkaProducer(
            bootstrap_servers=self.kafka_broker,
        )
        self.consumer = KafkaConsumer(
            group_id=None,
            client_id=f"{TOPIC}_{self._uuid}",
            bootstrap_servers=self.kafka_broker,
            enable_auto_commit=True,
            auto_offset_reset="earliest",
        )
        if self.is_anchor:
            self._id = 0
            self.consumer.assign([
                TopicPartition(DISCOVER, 0),
                TopicPartition(HEARTBEAT, 0),
                TopicPartition(f"{TOPIC}_{self._uuid}", 0)
            ])
        else:
            self.consumer.assign([
                TopicPartition(f"{TOPIC}_{self._uuid}", 0)
            ])
            self.producer.send(DISCOVER, pickle.dumps(self._uuid))
            self.producer.flush()
            res = self.consumer.poll(timeout_ms=10000, max_records=1)
            if len(res) == 0:
                raise TimeoutError("Timeout waiting for anchor node")
            msg = res.popitem()[1][0].value
            self._id, node_uuid, self._start_time = pickle.loads(msg)
            self.id_mapping[0] = node_uuid
        self.id_mapping[self.id] = self._uuid
        self.thread.start()


    def listen(self):
        last_time = time.time()
        while self.running:
            if time.time() - last_time > HEARTBEAT_INTERVAL:
                if self.is_anchor:
                    self.check_liveliness()
                else:
                    self.send_heartbeat()
                last_time = time.time()
            res = self.consumer.poll(timeout_ms=HEARTBEAT_INTERVAL * 1000)
            self.handle_msg(res)


    def send_heartbeat(self):
        self.producer.send(HEARTBEAT, self.id.to_bytes(4, "big") + bytes([1]))
        self.producer.flush()


    def handle_msg(self, res):
        for topic, msgs in res.items():
            for msg in msgs:
                if topic.topic == DISCOVER:
                    self.handle_discover(msg.value)
                elif topic.topic == HEARTBEAT:
                    self.handle_heartbeat(msg.value)
                else:
                    self.handle_recv(msg.value)


    def handle_discover(self, payload: bytes):
        node_uuid = pickle.loads(payload)
        self.total_nodes += 1
        self._nodes.add(self.total_nodes)
        Logger.log(Logger.JOIN, node_id=self.total_nodes)
        self.id_mapping[self.total_nodes] = node_uuid
        new_payload = (self.total_nodes, self._uuid, self.start_time)
        self.producer.send(f"{TOPIC}_{node_uuid}", pickle.dumps(new_payload))
        self.producer.flush()


    def handle_heartbeat(self, payload: bytes):
        node_id = int.from_bytes(payload[:4])
        keep = payload[4]
        if not keep:
            self.handle_disconect(node_id)
            return
        if node_id not in self.nodes:
            raise ValueError(f"Received message from unknown node {node_id}")
        self.hearbeats[node_id] = time.time()


    def handle_recv(self, payload: bytes):
        node_id = int.from_bytes(payload[:4])
        if node_id not in self.nodes:
            raise ValueError(f"Received message from unknown node {node_id}")
        data = payload[4:]
        Logger.log(Logger.RECV, sender=node_id, receiver=self.id, payload_size=len(data))
        if self.is_anchor:
            self.hearbeats[node_id] = time.time()
        self.q.put((node_id, data))


    def handle_disconect(self, node_id):
        uuid = self.id_mapping[node_id]
        Logger.log(Logger.LEAVE, node_id=node_id)
        self.admin.delete_topics([f"{TOPIC}_{uuid}"])
        self._nodes.remove(node_id)
        self.id_mapping.pop(node_id)
        self.hearbeats.pop(node_id, None)
        self.q.put((node_id, None))


    def check_liveliness(self):
        for node_id, last_time in list(self.hearbeats.items()):
            if node_id not in self.nodes:
                self.hearbeats.pop(node_id)
            if time.time() - last_time > TIMEOUT:
                self.handle_disconect(node_id)
