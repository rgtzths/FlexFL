from utils.CommABC import CommABC

class Zenoh(CommABC):
    
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)


    def imports(self) -> None:
        ...
