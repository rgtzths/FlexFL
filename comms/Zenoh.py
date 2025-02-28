import queue
import zenoh
from datetime import datetime
import pickle

from my_builtins.CommABC import CommABC

DISCOVER = "fl_discover"
LIVELINESS = "fl_liveliness"

class Zenoh(CommABC):
    

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.zconf = zenoh.Config()
        self.session = zenoh.open(self.zconf)
        self._id = None
        self._nodes = set()
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
        data = self.id.to_bytes(4) + data
        self.session.put(f"fl/{node_id}", data)


    def recv(self, node_id: int = None) -> tuple[int, bytes]:
        assert node_id is None, "Support for specific node_id not implemented"
        return self.q.get()
    

    def close(self) -> None:
        self.session.close()


    def handle_id(self, query: zenoh.Query):
        self.total_nodes += 1
        self._nodes.add(self.total_nodes)
        payload = (self.total_nodes, self.start_time)
        query.reply(query.key_expr, pickle.dumps(payload))


    def handle_liveliness(self, sample: zenoh.Sample):
        node_id = int(f"{sample.key_expr}".split("/")[-1])
        if sample.kind == zenoh.SampleKind.DELETE:
            self._nodes.remove(node_id)
            self.q.put((node_id, None))


    def handle_recv(self, sample: zenoh.Sample):
        data: bytes = sample.payload.to_bytes()
        node_id = int.from_bytes(data[:4])
        data = data[4:]
        self.q.put((node_id, data))


    def discover(self) -> None:
        replies = self.session.get(DISCOVER)
        for r in replies:
            self._id, self._start_time = pickle.loads(r.ok.payload.to_bytes())
            self.liveliness_token = self.session.liveliness().declare_token(f"{LIVELINESS}/{self.id}")
        if self.id is None:
            self._id = 0
            self._nodes.add(0)
            self.session.declare_queryable(DISCOVER, self.handle_id)
            self.liveliness_sub = self.session.liveliness().declare_subscriber(f"{LIVELINESS}/**", history=True, handler=self.handle_liveliness)
        self.sub = self.session.declare_subscriber(f"fl/{self._id}", self.handle_recv)