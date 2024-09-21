from time import time

from Utils.FLUtils import FLUtils

class DecentralizedAsync(FLUtils):
    
    def __init__(self, *,
        local_epochs = 3,
        alpha = 0.2,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.local_epochs = local_epochs
        self.alpha = alpha
        self.base_path += f'/{self.local_epochs}/{self.alpha}'


    def setup(self):
        self.ml.compile_model()

        if self.comm.is_master():
            self.x_val, self.y_val = self.ml.load_data('val')
            self.node_weights = [0] * self.comm.n_workers
            for _ in range(self.comm.n_workers):
                worker_id, n_samples = self.comm.recv_worker()
                self.node_weights[worker_id] = n_samples
            self.node_weights = [n_samples / sum(self.node_weights) for n_samples in self.node_weights]
            self.comm.send_workers(self.ml.get_weights())

        else:
            x_train, _ = self.ml.load_worker_data(self.comm.worker_id, self.comm.n_workers)
            n_samples = len(x_train)
            self.comm.send_master(n_samples)
            weights = self.comm.recv_master()
            self.ml.set_weights(weights)


    def master_train(self):
        ...



    def worker_train(self):
        ...

        

        