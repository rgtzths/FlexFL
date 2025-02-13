from utils.ImportsABC import ImportsABC, TYPE_CHECKING
from utils.CommABC import CommABC

if TYPE_CHECKING:
    ...

class Zenoh(CommABC, ImportsABC):
    
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)


    def imports(self) -> None:
        ...
