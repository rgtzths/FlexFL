from Utils.FLUtils import FLUtils

class CentralizedSync(FLUtils):


    def setup(self):
        
        if self.comm.is_master():
            self.x_val, self.y_val = self.ml.load_data('val')
            self.node_weights = [0] * self.comm.n_workers
            for _ in range(self.comm.n_workers):
                worker_id, n_batches = self.comm.recv_worker()
                self.node_weights[worker_id] = n_batches
            batches_sum = sum(self.node_weights)
            self.epoch_batches = batches_sum // self.comm.n_workers
            self.total_batches = self.epoch_batches * self.epochs
            self.node_weights = [n_batches / batches_sum for n_batches in self.node_weights]
            self.comm.send_workers(self.ml.get_weights())
        else:
            x_train, _ = self.ml.load_worker_data(self.comm.worker_id, self.comm.n_workers)
            n_samples = len(x_train)
            n_batches = n_samples // self.ml.batch_size
            self.comm.send_master(n_batches)
            weights = self.comm.recv_master()
            self.ml.set_weights(weights)

    
    def master_train(self):
        epoch = 0
        stop = False
        for batch in range(self.total_batches):
            avg_grads = []

            for _ in range(self.comm.n_workers):
                worker_id, grads = self.comm.recv_worker()

                if avg_grads == []:
                    avg_grads = [g * self.node_weights[worker_id] for g in grads]
                else:
                    avg_grads = [a + g * self.node_weights[worker_id] for a, g in zip(avg_grads, grads)]

            self.ml.apply_gradients(avg_grads)
            self.comm.send_workers(self.ml.get_weights())
            if batch % self.epoch_batches == 0:
                epoch += 1
                new_score = self.validate(epoch)
                stop = self.early_stop(new_score) or epoch == self.epochs
            self.comm.send_workers(stop)
            if stop:
                break


    def worker_train(self):
        stop = False
        while not stop:
            grads = self.ml.get_gradients()
            self.comm.send_master(grads)
            weights = self.comm.recv_master()
            self.ml.set_weights(weights)
            stop = self.comm.recv_master()
