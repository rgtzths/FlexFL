import queue
from datetime import datetime
import pickle

from my_builtins.CommABC import CommABC

DISCOVER = "fl/discover"
LIVELINESS = "fl_liveliness"

class Kafka(CommABC):
    
    def __init__(self, *, 
        ip: str = "localhost",
        port: int = 9092,
        **kwargs
    ) -> None:
        super().__init__(**kwargs)