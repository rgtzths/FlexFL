from typing import Any, Callable, Generator

from my_builtins.CommABC import CommABC
from my_builtins.MessageABC import MessageABC

class WorkerManager():

    MASTER_ID = 0

    def __init__(self, *, 
        c: CommABC,
        m: MessageABC,
        **kwargs
    ) -> None:
        self.c = c
        self.m = m
        self.worker_info = {}


    def send(self, worker_id: int, payload: Any) -> None:
        data = self.m.encode(payload)
        self.c.send(worker_id, data)


    def recv(self, worker_id: int=None) -> tuple[int, Any]:
        node_id, data = self.c.recv(worker_id)
        data = self.m.decode(data)
        return node_id, data
    

    def send_n(self, workers: list[int], payload: Any) -> None:
        data = self.m.encode(payload)
        for i in workers:
            self.c.send(i, data)


    def recv_n(self, workers: list[int], retry_fn: Callable = None) -> Generator:
        responses = {i: False for i in workers}
        while not all(responses.values()):
            node_id, data = self.recv()
            if self.set_info(node_id, data):
                continue
            if node_id not in responses:
                continue
            if data is not None:
                responses[node_id] = True
                yield node_id, data
                continue
            responses.pop(node_id)
            if retry_fn is None:
                continue
            new_id, new_data = retry_fn(self.worker_info, responses)
            if new_id is not None:
                self.send(node_id, new_data)


    def set_info(self, worker_id: int, info: dict) -> bool:
        if isinstance(info, dict) and info.get("type", None) == "worker_info":
            self.worker_info[worker_id] = info["data"]
            return True
        return False


    def wait_for_workers(self, n: int) -> None:
        while len(self.worker_info) < n:
            node_id, data = self.recv()
            self.set_info(node_id, data)
            

    def setup_worker_info(self, info: dict) -> None:
        self.send(0, {"type": "worker_info", "data": info})


    def get_subpool(self, size: int, fn: Callable) -> list[int]:
        return fn(size, self.worker_info)
