

class MLUtils:
    """
    Functions to implement in the child class:
    -
    """


    def __init__(self,
        prefix,
        optimizer,
        loss,
        dataset,
        batch_size,
        max_score,
        patience,
        delta,
        **kwargs
    ):
        self.prefix = prefix
        self.dataset = dataset
        self.optimizer = optimizer
        self.loss = loss
        self.batch_size = batch_size
        self.max_score = max_score
        self.patience = patience
        self.delta = delta
        self.model = self.get_model()


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