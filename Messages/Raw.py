from Utils.ImportsABC import ImportsABC
from Utils.MessageABC import MessageABC

class Raw(MessageABC, ImportsABC):
    """
    Raw encoding/decoding
    """

    def __init__(self):
        super().__init__()
        ImportsABC.__init__(self)


    def imports(self) -> None:
        return


    def encode(self, message: str) -> str:
        return message


    def decode(self, message: str) -> str:
        return message