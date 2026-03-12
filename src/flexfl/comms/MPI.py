from mpi4py import MPI as MPI4py
from datetime import datetime

from flexfl.builtins.CommABC import CommABC
from flexfl.builtins.Logger import Logger


class MPI(CommABC):

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.comm = MPI4py.COMM_WORLD
        self._id = self.comm.Get_rank()
        self._nodes = set(range(self.comm.Get_size()))
        if len(self._nodes) == 1:
            raise ValueError("Only one node found. Please run with multiple processes.")
        self._start_time = datetime.now()
        self.status = MPI4py.Status()
        self.setup()


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
        self.comm.send(data, dest=node_id, tag=0)


    def recv(self, node_id: int = None) -> tuple[int, bytes]:
        if node_id is None:
            data = self.comm.recv(source=MPI4py.ANY_SOURCE, tag=0, status=self.status)
            node_id = self.status.Get_source()
        else:
            data = self.comm.recv(source=node_id, tag=0)
        if data is None:
            Logger.log(Logger.LEAVE, node_id=node_id)
            return node_id, None
        Logger.log(Logger.RECV, sender=node_id, receiver=self.id, payload_size=len(data))
        return node_id, data
    

    def close(self) -> None:
        if self.id != 0:
            self.comm.send(None, dest=0, tag=0)
    

    def setup(self):
        self._start_time = self.comm.bcast(self._start_time, root=0)
        if self.id != 0:
            return
        for i in range(1, len(self._nodes)):
            Logger.log(Logger.JOIN, node_id=i)
            