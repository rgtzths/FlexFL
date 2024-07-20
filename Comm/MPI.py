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


    def is_master(self):
        return self.rank == 0
    

    def send_master(self, data):
        self.comm.send(self.pickle.dumps(data), dest=0)


    def recv_master(self):
        data = self.comm.recv(source=0)
        return self.pickle.loads(data)
    

    def send_worker(self, worker_id, data):
        data = self.pickle.dumps(data)
        self.comm.send(data, dest=worker_id+1)
    

    def send_workers(self, data):
        data = self.pickle.dumps(data)
        for i in range(1, self.size):
            self.comm.send(data, dest=i)


    def recv_worker(self):
        data = self.comm.recv(source=MPI4py.ANY_SOURCE, status=self.status)
        return (self.status.Get_source()-1, self.pickle.loads(data))
        