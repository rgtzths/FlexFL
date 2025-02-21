import pickle

from my_builtins.MessageABC import MessageABC

class Raw(MessageABC):
    """
    Raw encoding/decoding
    """

    def encode(self, message: any) -> bytes:
        return pickle.dumps(message)


    def decode(self, message: bytes) -> any:
        return pickle.loads(message)