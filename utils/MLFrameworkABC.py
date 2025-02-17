from abc import ABC, abstractmethod


class MLFrameworkABC(ABC):

    def __init__(self, *,
        var1: int = 1,
        var2: str = "hello",
        var3: bool = False,
        **kwargs
    ) -> None:
        ...
