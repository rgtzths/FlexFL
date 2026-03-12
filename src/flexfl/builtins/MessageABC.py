from abc import ABC, abstractmethod
from typing import Any

class MessageABC(ABC):
    """
    Message layer abstract base class
    """

    def __init__(self, **kwargs) -> None:
        return
    

    @abstractmethod
    def encode(self, message: Any) -> bytes:
        """
        Encodes the message
        """
        pass
    

    @abstractmethod
    def decode(self, message: Any) -> bytes:
        """
        Decodes the message
        """
        pass