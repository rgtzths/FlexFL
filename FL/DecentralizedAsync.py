from time import time

from Utils.FLUtils import FLUtils

class DecentralizedAsync(FLUtils):
    
    def __init__(self, *,
        local_epochs = 3,
        alpha = 0.5,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.local_epochs = local_epochs
        self.alpha = alpha
        self.base_path += f'/{self.local_epochs}/{self.alpha}'
        self.current_version = 0
        self.workers_versions = [0] * self.comm.n_workers


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


    def penalty(self, worker_id):
        # delay_penalty = (self.current_version - self.workers_versions[worker_id]) / self.comm.n_workers + 1
        # print(self.alpha, self.node_weights[worker_id])
        # print(self.node_weights[worker_id] * self.alpha)
        # return self.alpha * self.node_weights[worker_id]
        return 0.8 


    def master_train(self):
        exited_workers = 0
        stop = False
        epoch = 0

        while exited_workers < self.comm.n_workers:
            worker_id, weights = self.comm.recv_worker()
            local_weights = self.ml.get_weights()

            weight_diffs = [ 
                (weight - local_weights[idx])*self.penalty(worker_id)
                for idx, weight in enumerate(weights)
            ]
            local_weights = [
                local_weights[idx] + weight
                for idx, weight in enumerate(weight_diffs)
            ]

            self.ml.set_weights(local_weights)
            self.comm.send_worker(worker_id, weight_diffs)
            self.current_version += 1
            self.workers_versions[worker_id] = self.current_version
            old_epoch = epoch
            epoch += self.node_weights[worker_id]
            if int(epoch) > int(old_epoch):
                new_score = self.validate(int(epoch))
                stop = self.early_stop(new_score) or int(epoch) == self.epochs
            self.comm.send_worker(worker_id, stop)
            if stop:
                exited_workers +=1


    def worker_train(self):
        stop = False
        while not stop:
            self.ml.train(self.local_epochs)
            weights = self.ml.get_weights()
            self.comm.send_master(weights)
            new_weights = self.comm.recv_master()
            self.ml.set_weights(new_weights)
            stop = self.comm.recv_master()
