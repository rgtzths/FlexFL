from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

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