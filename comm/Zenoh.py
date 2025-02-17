from utils.ImportsABC import ImportsABC
from utils.CommABC import CommABC

class Zenoh(CommABC, ImportsABC):
    
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)


    def imports(self) -> None:
        ...
