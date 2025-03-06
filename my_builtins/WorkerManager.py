from typing import Any, Callable, Generator

from my_builtins.CommABC import CommABC
from my_builtins.MessageABC import MessageABC

JOIN_TYPE = "__joining__"
WAITING_TYPE = "__waiting__"

class WorkerManager():

    MASTER_ID = 0
    EXIT_TYPE = "exit"

    def __init__(self, *, 
        c: CommABC,
        m: MessageABC,
        **kwargs
    ) -> None:
        self.c = c
        self.m = m
        self.worker_info = {}
        self.callbacks: dict[str, Callable[[int, Any], None]] = {}
        self.on_joining: Callable[[], None] = self.default_on_joining
        self.on_new_worker: Callable[[int, dict], None] = self.default_on_new_worker
        self.on_worker_disconnect: Callable[[int], None] = self.default_on_worker_disconnect


    @property
    def n_workers(self) -> int:
        return len(self.worker_info)
    

    def get_info(self, node_id: int) -> dict:
        return self.worker_info[node_id]


    def set_callbacks(self, *data: tuple[str, Callable[[int, Any], None]]) -> None:
        for type_, fn in data:
            self.callbacks[type_] = fn


    def handle_recv(self, node_id: int, data: Any, type_: str) -> None:
        if type_ in self.callbacks:
            self.callbacks[type_](node_id, data)
        elif type_ == JOIN_TYPE:
            self.worker_info[node_id] = data
            self.on_new_worker(node_id, data)
        else:
            raise ValueError(f"No callback for type {type_}")


    def get_all_workers(self) -> list[int]:
        return list(self.c.nodes - {0})


    def send(self, worker_id: int, payload: Any = None, type_: str = None) -> None:
        payload = {"type": type_, "data": payload}
        data = self.m.encode(payload)
        self.c.send(worker_id, data)


    def _recv(self, type_: str = None, return_on_disconnect: bool = False) -> tuple[int, Any]:
        node_id, data = self.c.recv()
        if data is None:
            self.on_worker_disconnect(node_id)
            if return_on_disconnect:
                return node_id, None
            return None
        data = self.m.decode(data)
        if not isinstance(data, dict) and "type" not in data:
            raise ValueError(f"Wrong data format: {data}")
        msg_type = data["type"]
        payload = data["data"]
        if (
            (type_ is None and msg_type != JOIN_TYPE) or
            (msg_type == type_ )
        ):
            return node_id, payload
        else:
            self.handle_recv(node_id, payload, msg_type)
        return None


    def recv(self, type_: str = None, return_on_disconnect: bool = False) -> tuple[int, Any]:
        while True:
            res = self._recv(type_, return_on_disconnect)
            if res is not None:
                return res
    

    def send_n(self, workers: list[int], payload: Any = None, type_: str = None) -> None:
        payload = {"type": type_, "data": payload}
        data = self.m.encode(payload)
        for i in workers:
            self.c.send(i, data)


    def recv_n(self, 
        workers: list[int], 
        type_: str = None, 
        retry_fn: Callable[[dict, dict], tuple[int, Any, str]] = None,
        return_on_disconnect: bool = False
    ) -> Generator:
        responses = {i: False for i in workers}
        while not all(responses.values()):
            node_id, data = self.recv(type_, True)
            if data is not None:
                responses[node_id] = True
                yield node_id, data
                continue
            responses.pop(node_id)
            if retry_fn is None:
                if return_on_disconnect:
                    yield node_id, None
                continue
            new_id, new_data, new_type = retry_fn(self.worker_info, responses)
            if new_id is not None:
                responses[new_id] = False
                self.send(node_id, new_data, new_type)
            elif return_on_disconnect:
                yield node_id, None


    def wait_for_workers(self, n: int) -> None:
        while len(self.worker_info) < n:
            self._recv(WAITING_TYPE)
            

    def setup_worker_info(self, info: dict) -> None:
        self.send(WorkerManager.MASTER_ID, info, JOIN_TYPE)
        self.on_joining()


    def get_subpool(self, size: int, fn: Callable[[int, dict], list[int]]) -> list[int]:
        return fn(size, self.worker_info)
    

    def default_on_joining(self) -> None:
        return
    

    def default_on_new_worker(self, node_id: int, worker_info: dict) -> None:
        return
    

    def default_on_worker_disconnect(self, node_id: int) -> None:
        return
