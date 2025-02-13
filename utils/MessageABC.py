from abc import ABC, abstractmethod

class MessageABC(ABC):
    """
    Message layer abstract base class
    """

    def __init__(self, **kwargs) -> None:
        return
    

    @abstractmethod
    def encode(self, message: str) -> str:
        """
        Encodes the message
        """
        pass
    

    @abstractmethod
    def decode(self, message: str) -> str:
        """
        Decodes the message
        """
        pass