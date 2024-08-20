import pprint
from pathlib import Path

CLASSIFICATIONS = {'scc'}

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
        seed = 42,
        **kwargs
    ):
        self.ml = ml
        self.comm = comm
        self.epochs = epochs
        self.max_score = max_score
        self.patience = patience
        self.delta = delta
        self.stop = False
        self.seed = seed
        self.is_classification = self.ml.loss_name in CLASSIFICATIONS
        self.patience_buffer = [0] * self.patience
        self.all_results = []

        self.base_path = (
            'Results/' +
            f'{self.ml.dataset.__class__.__name__}/' +  # dataset
            f'{self.__class__.__name__}/' +             # fl
            f'{self.comm.__class__.__name__}/' +        # comm
            f'{self.comm.n_workers}/' +                 # n_workers
            f'{self.ml.prefix}/' +                      # ml prefix
            f'{self.seed}/' +                           # seed
            f'{self.ml.optimizer_name}/' +              # optimizer
            f'{self.ml.batch_size}/' +                  # batch_size
            f'{self.epochs}'                            # epochs
        )


    def create_base_path(self):
        if self.comm.is_master():
            Path(self.base_path).mkdir(parents=True, exist_ok=True)


    def __str__(self):
        return pprint.pformat(vars(self))