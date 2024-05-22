import pprint

class MLUtils:
    """
    Functions to implement in the child class:
    - init(self)
    """

    def __init__(self, *,
        model,
        dataset,
        optimizer,
        loss,
        learning_rate = 0.001,
        batch_size = 32,
        max_score = 0.99,
        patience = 5,
        delta = 0.01,
        **kwargs
    ):
        self.prefix = None
        self.dataset = dataset
        self.optimizer = optimizer
        self.loss = loss
        self.learning_rate = learning_rate
        self.batch_size = batch_size
        self.max_score = max_score
        self.patience = patience
        self.delta = delta
        self.init()
        self.model = model.get_model(self.prefix, self.dataset)


    def call_fn(self, fn, *args, **kwargs):
        if hasattr(self.dataset, fn):
            return getattr(self.dataset, fn)(*args, **kwargs)
        else:
            raise NotImplementedError(f"{fn} not implemented in {self.dataset.name}")


    def get_model(self):
        return self.call_fn(f"{self.prefix}_model")
    

    def load_data(self, split):
        return self.call_fn(f"{self.prefix}_data", split)
    

    def load_worker_data(self, worker_id, num_workers):
        return self.call_fn(f"{self.prefix}_worker_data", worker_id, num_workers)
    

    def __str__(self):
        return pprint.pformat(vars(self))