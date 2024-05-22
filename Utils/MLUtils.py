import pprint

class MLUtils:
    """
    Functions to implement in the child class:
    - init(self)
    - load_data(self, split)
    - load_worker_data(self, worker_id, num_workers)
    - get_weights(self)
    - set_weights(self, weights)
    - get_gradients(self)
    - apply_gradients(self, gradients)
    - train(self, epochs)
    - evaluate(self, split)
    - save_model(self, path)
    - load_model(self, path)
    """

    def __init__(self, *,
        model,
        dataset,
        optimizer = 'adam',
        loss = 'scc',
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
    

    def __str__(self):
        return pprint.pformat(vars(self))