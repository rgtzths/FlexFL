from abc import ABC, abstractmethod

class MessageABC(ABC):
    """
    Message layer abstract base class
    """

    def __init__(self, **kwargs) -> None:
        return
    

    @abstractmethod
    def encode(self, message: any) -> bytes:
        """
        Encodes the message
        """
        pass
    

    @abstractmethod
    def decode(self, message: any) -> bytes:
        """
        Decodes the message
        """
        pass