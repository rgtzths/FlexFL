from abc import ABC, abstractmethod

class CommABC(ABC):
    """
    Communication layer abstract base class
    """

    def __init__(self, **kwargs) -> None:
        return