from typing import Any, Callable, Generator

from my_builtins.CommABC import CommABC
from my_builtins.MessageABC import MessageABC

class WorkerManager():

    def __init__(self, *, 
        c: CommABC,
        m: MessageABC,
        **kwargs
    ) -> None:
        self.c = c
        self.m = m
        self.working = {}


    def get_subpool(self, size: int, fn: Callable) -> list[int]:
        return fn(size, self.c.nodes)
    

    def send(self, workers: list[int], payload: Any) -> None:
        data = self.m.encode(payload)
        for i in workers:
            self.c.send(i, data)


    def recv(self):
        node_id, data = self.c.recv()
        return node_id, self.m.decode(data) if data else None


    def send_and_recv(self, 
        workers: list[int], 
        payload: Any,
        retry: Callable = None
    ) -> Generator:
        self.send(workers, payload)
        if retry is None:
            yield from (self.recv() for _ in workers)
            return
        
        finished = {i: False for i in workers}
        while not all(finished.values()):
            node_id, data = self.recv()

            if node_id not in finished:
                continue

            if data is not None:
                finished[node_id] = True
                yield node_id, data
                continue
            
            finished.pop(node_id)
            new_node = retry(finished, self.c.nodes)
            if new_node is None:
                yield None, None
            else:
                self.send([new_node], payload)
                finished[new_node] = False
    
    
