from abc import ABC, abstractmethod

class ImportsABC(ABC):
    """
    Dynamic imports abstract base class
    """

    def __init__(self):
        try:
            self.imports()
        except Exception as e:
            print(f"Error importing modules: {e}")
            exit(1)


    @abstractmethod
    def imports(self) -> None:
        """
        Imports the necessary modules
        """
        pass