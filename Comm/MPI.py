from mpi4py import MPI as MPI4py
import sys

from Utils.CommUtils import CommUtils

class MPI(CommUtils):

    def __init__(self):
        self.comm = MPI4py.COMM_WORLD
        self.rank = self.comm.Get_rank()
        self.size = self.comm.Get_size()
        self.n_workers = self.size - 1
        self.worker_id = self.rank - 1
        self.status = MPI4py.Status()
        self.pickle =  MPI4py.pickle


    def set_buffer(self, data):
        self.buffer = self.pickle.dumps(data)


    def is_master(self):
        return self.rank == 0
    

    def send_master(self):
        self.comm.send(self.buffer, dest=0)


    def recv_master(self):
        if not isinstance(self.buffer, bytearray):
            self.buffer = bytearray(sys.getsizeof(self.buffer))
        self.comm.recv(self.buffer, source=0)
        return self.pickle.loads(self.buffer)
    

    def send_worker(self, worker_id):
        self.comm.send(self.buffer, dest=worker_id)


    def recv_worker(self):
        if not isinstance(self.buffer, bytearray):
            self.buffer = bytearray(sys.getsizeof(self.buffer))
        self.comm.recv(self.buffer, source=MPI4py.ANY_SOURCE, status=self.status)
        return (self.status.Get_source()-1, self.pickle.loads(self.buffer))
        