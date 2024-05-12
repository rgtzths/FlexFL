

class Base:
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


    def get_model(self):
        return self.dataset.call_fn(f"{self.prefix}_model")
    

    def load_data(self, split):
        return self.dataset.call_fn(f"{self.prefix}_data", split)
    

    def load_worker_data(self, worker_id, num_workers):
        return self.dataset.call_fn(f"{self.prefix}_worker_data", worker_id, num_workers)