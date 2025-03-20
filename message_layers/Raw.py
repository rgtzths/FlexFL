import pickle
from typing import Any

from my_builtins.MessageABC import MessageABC
from my_builtins.Logger import Logger

class Raw(MessageABC):
    """
    Raw encoding/decoding
    """

    @Logger.encode
    def encode(self, message: Any) -> bytes:
        return pickle.dumps(message)


    @Logger.decode
    def decode(self, message: bytes) -> Any:
        return pickle.loads(message)