from abc import ABC, abstractmethod

class MessageABC(ABC):
    """
    Message layer abstract base class
    """

    def __init__(self,
        b,
        a: int = 1,
        **kwargs
    ):
        ...

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