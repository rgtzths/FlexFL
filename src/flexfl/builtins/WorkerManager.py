from typing import Any, Callable, Generator

from flexfl.builtins.CommABC import CommABC
from flexfl.builtins.MessageABC import MessageABC
from flexfl.builtins.Logger import Logger

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
        self.buffer: dict[Any, list[tuple[int, Any]]] = {}


    @property
    def n_workers(self) -> int:
        return len(self.worker_info)
    

    def get_info(self, node_id: int) -> dict:
        return self.worker_info[node_id]


    def set_callbacks(self, *data: tuple[str, Callable[[int, Any], None]]) -> None:
        for type_, fn in data:
            self.callbacks[type_] = fn


    def handle_recv(self, node_id: int, data: Any, type_: Any) -> None:
        if type_ in self.callbacks:
            self.callbacks[type_](node_id, data)
        elif type_ == JOIN_TYPE:
            self.worker_info[node_id] = data
            Logger.log(Logger.NEW_WORKER, node_id=node_id, info=data)
            self.on_new_worker(node_id, data)
        else:
            if type_ not in self.buffer:
                self.buffer[type_] = []
            self.buffer[type_].append((node_id, data))


    def get_all_workers(self) -> list[int]:
        return list(self.c.nodes - {0})


    def send(self, node_id: int, payload: Any = None, type_: Any = None) -> None:
        if node_id not in self.c.nodes:
            return
        payload = {"type": type_, "data": payload}
        data = self.m.encode(payload)
        self.c.send(node_id, data)


    def _recv(self, type_: Any = None, return_on_disconnect: bool = False) -> tuple[int, Any]:
        node_id, data = self.c.recv()
        if data is None:
            if node_id not in self.worker_info:
                return None
            self.worker_info.pop(node_id)
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


    def recv(self, type_: Any = None, return_on_disconnect: bool = False) -> tuple[int, Any]:
        while True:
            if type_ is None:
                for type_, data in list(self.buffer.items()):
                    if len(data) > 0:
                        return data.pop(0)
            elif type_ in self.buffer and len(self.buffer[type_]) > 0:
                return self.buffer[type_].pop(0)
            res = self._recv(type_, return_on_disconnect)
            if res is not None:
                return res
    

    def send_n(self, workers: list[int], payload: Any = None, type_: Any = None) -> None:
        payload = {"type": type_, "data": payload}
        data = self.m.encode(payload)
        for i in workers:
            if i in self.c.nodes:
                self.c.send(i, data)


    def recv_n(self, 
        workers: list[int], 
        type_: Any = None, 
        reschedule_fn: Callable[[dict, dict], tuple[int, Any, str]] = None,
        return_on_disconnect: bool = False
    ) -> Generator:
        responses = {i: False for i in workers}
        while not all(responses.values()):
            node_id, data = self.recv(type_, True)
            if node_id not in responses and data is None:
                continue
            if data is not None:
                responses[node_id] = True
                yield node_id, data
                continue
            responses.pop(node_id)
            if reschedule_fn is not None:
                new_id, new_data, new_type = reschedule_fn(self.worker_info, responses)
                if new_id is not None:
                    responses[new_id] = False
                    self.send(node_id, new_data, new_type)
                    continue
            if return_on_disconnect:
                yield node_id, None


    def end(self) -> None:
        self.send_n(
            workers = self.get_all_workers(), 
            type_ = WorkerManager.EXIT_TYPE
        )


    def loop_once(self) -> None:
        self._recv(WAITING_TYPE)


    def wait_for_workers(self, n: int) -> None:
        while len(self.worker_info) < n:
            self.loop_once()


    def wait_for(self, condition: Callable[[], bool]) -> None:
        while not condition():
            self.loop_once()
            

    def setup_worker_info(self, info: dict) -> None:
        self.send(WorkerManager.MASTER_ID, info, JOIN_TYPE)
        self.on_joining()


    def get_subpool(self, size: int, fn: Callable[[int, dict], list[int]]) -> list[int]:
        return fn(size, self.worker_info)
    

    def default_on_joining(self) -> None:
        return
    

    def default_on_new_worker(self, worker_id: int, worker_info: dict) -> None:
        return
    

    def default_on_worker_disconnect(self, worker_id: int) -> None:
        return
