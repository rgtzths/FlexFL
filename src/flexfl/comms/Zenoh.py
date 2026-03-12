import queue
import zenoh
from datetime import datetime
import pickle

from flexfl.builtins.CommABC import CommABC
from flexfl.builtins.Logger import Logger

DISCOVER = "fl_discover"
LIVELINESS = "fl_liveliness"

class Zenoh(CommABC):
    

    def __init__(self, *, 
        ip: str = "localhost",
        zenoh_port: int = 7447,
        is_anchor: bool = False,
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.is_anchor = is_anchor
        if ip == "localhost":
            ip ="0.0.0.0"
        enpoint = str([f"tcp/{ip}:{zenoh_port}"])
        self.zconf = zenoh.Config()
        if is_anchor:
            self.zconf.insert_json5("listen/endpoints", enpoint)
        else:
            self.zconf.insert_json5("connect/endpoints", enpoint)
        self.session = zenoh.open(self.zconf)
        self._id = None
        self._nodes = {0}
        self._start_time = datetime.now()
        self.total_nodes = 0
        self.q = queue.Queue()
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
        self.session.put(f"fl/{node_id}", data)


    def recv(self, node_id: int = None) -> tuple[int, bytes]:
        assert node_id is None, "Support for specific node_id not implemented"
        node_id, data = self.q.get()
        return node_id, data
    

    def close(self) -> None:
        self.session.close()


    def handle_id(self, query: zenoh.Query):
        self.total_nodes += 1
        Logger.log(Logger.JOIN, node_id=self.total_nodes)
        self._nodes.add(self.total_nodes)
        payload = (self.total_nodes, self.start_time)
        query.reply(query.key_expr, pickle.dumps(payload))


    def handle_liveliness(self, sample: zenoh.Sample):
        node_id = int(f"{sample.key_expr}".split("/")[-1])
        if sample.kind == zenoh.SampleKind.DELETE:
            Logger.log(Logger.LEAVE, node_id=node_id)
            self._nodes.remove(node_id)
            self.q.put((node_id, None))


    def handle_recv(self, sample: zenoh.Sample):
        data: bytes = sample.payload.to_bytes()
        node_id = int.from_bytes(data[:4])
        if node_id not in self.nodes:
            raise ValueError(f"Received message from unknown node {node_id}")
        data = data[4:]
        Logger.log(Logger.RECV, sender=node_id, receiver=self.id, payload_size=len(data))
        self.q.put((node_id, data))


    def discover(self) -> None:
        if self.is_anchor:
            self._id = 0
            self.discover_queryable = self.session.declare_queryable(DISCOVER, self.handle_id)
            self.liveliness_sub = self.session.liveliness().declare_subscriber(f"{LIVELINESS}/**", history=True, handler=self.handle_liveliness)
        else:
            replies = self.session.get(DISCOVER)
            for r in replies:
                self._id, self._start_time = pickle.loads(r.ok.payload.to_bytes())
                self.liveliness_token = self.session.liveliness().declare_token(f"{LIVELINESS}/{self.id}")
            if self.id is None:
                raise TimeoutError("Failed to discover the master node")
        self.sub = self.session.declare_subscriber(f"fl/{self._id}", self.handle_recv)