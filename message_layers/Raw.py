import pickle
from typing import Any


from my_builtins.MessageABC import MessageABC

class Raw(MessageABC):
    """
    Raw encoding/decoding
    """

    def encode(self, message: Any) -> bytes:
        return pickle.dumps(message)


    def decode(self, message: bytes) -> Any:
        return pickle.loads(message)