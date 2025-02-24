
from my_builtins.FederatedABC import FederatedABC
from my_builtins.WorkerManager import WorkerManager


class DecentralizedSync(FederatedABC):


    def master_setup(self):
        self.ml.compile_model()
        self.x_val, self.y_val = self.ml.load_data("val")


    def worker_setup(self):
        self.ml.compile_model()
        self.ml.load_worker_data(self.id, 8)


    def get_worker_info(self) -> dict:
        return {
            "n_samples": self.ml.n_samples,
        }


    def master_loop(self):
        self.wm.wait_for_workers(self.min_workers)
        for epoch in range(1, self.epochs+1):
            pool = self.wm.get_subpool(self.min_workers, self.random_pool)
            self.wm.send_n(pool, self.ml.get_weights())
            weights = None
            for _, data in self.wm.recv_n(pool):
                if weights is None:
                    weights = data / len(pool)
                else:
                    weights += data / len(pool)
            self.ml.set_weights(weights)
            self.validate(epoch, self.x_val, self.y_val)
            stop = self.early_stop() or epoch == self.epochs
            if stop:
                self.wm.send_n(self.wm.worker_info.keys(), None)
                break


    def worker_run(self, weights):
        self.ml.set_weights(weights)
        self.ml.train(self.epochs)
        self.wm.send(WorkerManager.MASTER_ID, self.ml.get_weights())

