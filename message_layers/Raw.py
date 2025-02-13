from utils.MessageABC import MessageABC

class Raw(MessageABC):
    """
    Raw encoding/decoding
    """

    def encode(self, message: str) -> str:
        return message


    def decode(self, message: str) -> str:
        return message