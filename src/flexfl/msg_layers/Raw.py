import pickle
from typing import Any

from flexfl.builtins.MessageABC import MessageABC
from flexfl.builtins.Logger import Logger

class Raw(MessageABC):
    """
    Raw encoding/decoding
    """

    @Logger.time(Logger.ENCODE)
    def encode(self, message: Any) -> bytes:
        return pickle.dumps(message)


    @Logger.time(Logger.DECODE) 
    def decode(self, message: bytes) -> Any:
        return pickle.loads(message)