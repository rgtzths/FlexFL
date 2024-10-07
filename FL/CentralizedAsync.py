from Utils.FLUtils import FLUtils

class CentralizedAsync(FLUtils):

    def __init__(self, *,
        alpha = 0.5,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.alpha = alpha
        self.base_path += f'/{self.alpha}'
        self.current_version = 0
        self.workers_versions = [0] * self.comm.n_workers


    def setup(self):
        
        if self.comm.is_master():
            self.x_val, self.y_val = self.ml.load_data('val')
            self.node_weights = [0] * self.comm.n_workers
            for _ in range(self.comm.n_workers):
                worker_id, n_batches = self.comm.recv_worker()
                self.node_weights[worker_id] = n_batches
            batches_sum = sum(self.node_weights)
            self.epoch_batches = batches_sum // self.comm.n_workers
            # self.total_batches = self.epoch_batches * self.epochs
            self.node_weights = [n_batches / batches_sum for n_batches in self.node_weights]
            self.comm.send_workers(self.ml.get_weights())
        else:
            x_train, _ = self.ml.load_worker_data(self.comm.worker_id, self.comm.n_workers)
            n_samples = len(x_train)
            n_batches = n_samples // self.ml.batch_size
            self.comm.send_master(n_batches)
            weights = self.comm.recv_master()
            self.ml.set_weights(weights)


    def penalty(self, worker_id):
        return 0.8


    def master_train(self):
        epoch = 0
        stop = False
        exited_workers = 0
        batch = 0

        while exited_workers < self.comm.n_workers:
            batch += 1
            worker_id, grads = self.comm.recv_worker()
            grads = [g * self.penalty(worker_id) for g in grads]
            self.ml.apply_gradients(grads)
            self.comm.send_worker(worker_id, self.ml.get_weights())

            if batch % self.epoch_batches == 0:
                epoch += 1
                new_score = self.validate(epoch)
                stop = self.early_stop(new_score) or epoch == self.epochs
            self.comm.send_worker(worker_id, stop)
            if stop:
                exited_workers += 1
    
    
    def worker_train(self):
        stop = False
        while not stop:
            grads = self.ml.get_gradients()
            self.comm.send_master(grads)
            weights = self.comm.recv_master()
            self.ml.set_weights(weights)
            stop = self.comm.recv_master()
