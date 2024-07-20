import pprint
from pathlib import Path

class FLUtils:
    """
    Methods to implement in the child class:
    - run(self)
    """

    def __init__(self, *, 
        ml, 
        comm, 
        epochs = 10,
        max_score = 0.99,
        patience = 5,
        delta = 0.01,
        **kwargs
    ):
        self.ml = ml
        self.comm = comm
        self.epochs = epochs
        self.max_score = max_score
        self.patience = patience
        self.delta = delta
        self.stop = False
        self.patience_buffer = [0] * self.patience

        self.base_path = f'Results/{self.ml.dataset.__class__.__name__}/{self.__class__.__name__}/{self.comm.__class__.__name__}_{self.comm.n_workers}/{self.ml.prefix}_{self.ml.optimizer_name}_{self.ml.batch_size}_{self.epochs}'


    def create_base_path(self):
        if self.comm.is_master():
            Path(self.base_path).mkdir(parents=True, exist_ok=True)


    def __str__(self):
        return pprint.pformat(vars(self))