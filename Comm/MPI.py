from mpi4py import MPI as MPI4py
import sys
from time import time

from Utils.CommUtils import CommUtils
from Utils.Logger import Logger


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
    

    @Logger.send
    def send_master(self, data):
        self.comm.send(data, dest=0)


    @Logger.recv
    def recv_master(self):
        return self.comm.recv(source=0)
    

    @Logger.send
    def send_worker(self, worker_id, data):
        self.comm.send(data, dest = worker_id + 1)
    

    @Logger.recv
    def recv_worker(self):
        data = self.comm.recv(source=MPI4py.ANY_SOURCE, status=self.status)
        return (self.status.Get_source()-1, data)
        

    def get_size(self, data):
        return sys.getsizeof(self.pickle.dumps(data))