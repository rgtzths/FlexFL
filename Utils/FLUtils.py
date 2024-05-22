import pprint

class FLUtils:
    """
    Methods to implement in the child class:
    - run(self)
    """

    def __init__(self, *, 
        ml, 
        comm, 
        epochs = 10,
        **kwargs
    ):
        self.ml = ml
        self.comm = comm
        self.epochs = epochs


    def __str__(self):
        return pprint.pformat(vars(self))