from abc import ABC, abstractmethod

class ImportsABC(ABC):
    """
    Dynamic imports abstract base class
    """

    @abstractmethod
    def imports(self) -> None:
        """
        Imports the necessary modules
        """
        pass