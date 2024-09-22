import pprint
from abc import ABC, abstractmethod
from typing import Optional

class CommUtils(ABC):

    def __init__(self,
        **kwargs
    ):
        self.n_workers: Optional[int] = None
        self.worker_id: Optional[int] = None


    @abstractmethod
    def is_master(self) -> bool:
        """
        Checks if the current process is the master process

        Returns:
            bool: True if the current process is the master process, False otherwise
        """
        pass


    @abstractmethod
    def send_master(self, data: any) -> None:
        """
        Sends data to the master process

        Parameters:
            data (any): the data to send
        """
        pass


    @abstractmethod
    def recv_master(self):
        """
        Receives data from the master process

        Returns:
            any: the received data
        """
        pass


    @abstractmethod
    def send_worker(self, worker_id: int, data: any) -> None:
        """
        Sends data to a worker process

        Parameters:
            worker_id (int): the id of the worker process
            data (any): the data to send
        """
        pass


    @abstractmethod
    def recv_worker(self) -> tuple[int, any]:
        """
        Receives data from any worker process

        Returns:
            tuple (int, any): the id of the worker process and the received data
        """
        pass


    @abstractmethod
    def get_size(self, data: any) -> int:
        """
        Get the size of the data

        Parameters:
            data (any): the data to get the size of

        Returns:
            int: the size of the data
        """
        pass


    def send_workers(self, data: any) -> None:
        """
        Sends data to all worker processes

        Parameters:
            data (any): the data to send
        """
        for worker_id in range(self.n_workers):
            self.send_worker(worker_id, data)


    def __str__(self):
        return pprint.pformat(vars(self))