
from typing import TypedDict, Optional, Any


# class M:

#     def __init__(self, *,
#         arg1: float = 1.0,
#         arg2: str = "a",
#         **kwargs
#     ):
#         self.arg1 = arg1
#         self.arg2 = arg2

class M(TypedDict, total=False):
    arg1: float
    arg2: str


class N(M):

    def __init__(self, *,
        arg3: int = 42,
        **kwargs: M | dict[str, Any]
    ):
        super().__init__(**kwargs)
        self.arg3 = arg3




N()
