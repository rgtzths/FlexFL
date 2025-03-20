from abc import ABC, abstractmethod
from datetime import datetime

class CommABC(ABC):
    """
    Communication layer abstract base class
    """

    def __init__(self, **kwargs) -> None:
        return
    

    @property
    @abstractmethod
    def id(self) -> int:
        """
        Returns the id of the node
        """
        pass


    @property
    @abstractmethod
    def nodes(self) -> set[int]:
        """
        Returns the set of nodes
        """
        pass

    
    @property
    @abstractmethod
    def start_time(self) -> datetime:
        """
        Returns the start time of the communication layer
        """
        pass


    @abstractmethod
    def send(self, node_id: int, data: bytes) -> None:
        """
        Sends data to a node
        """
        pass


    @abstractmethod
    def recv(self, node_id: int = None) -> tuple[int, bytes]:
        """
        Receives data from a node, if node_id is None, receives from any node
        
        Returns the node_id and the data, if a node dies, data is None
        """
        pass


    @abstractmethod
    def close(self) -> None:
        """
        Closes the communication layer
        """
        pass

    
    @property
    def num_nodes(self) -> int:
        """
        Returns the number of nodes
        """
        return len(self.nodes)