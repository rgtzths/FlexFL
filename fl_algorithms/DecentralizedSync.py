
from my_builtins.FederatedABC import FederatedABC
from my_builtins.WorkerManager import WorkerManager


class DecentralizedSync(FederatedABC):


    def setup(self):
        self.ml.compile_model()
        if self.is_master:
            self.x_val, self.y_val = self.ml.load_data("val")
        else:
            self.ml.load_worker_data(self.id, 8)
        self.wm.set_callbacks(
            ("work", self.on_work)
        )


    def get_worker_info(self) -> dict:
        return {
            "n_samples": self.ml.n_samples,
        }


    def master_loop(self):
        for epoch in range(1, self.epochs+1):
            self.wm.wait_for_workers(self.min_workers)
            pool = self.wm.get_subpool(self.min_workers, self.random_pool)
            self.wm.send_n(pool, self.ml.get_weights(), "work")
            weighted_sum = 0
            total_weight = 0
            for worker_id, data in self.wm.recv_n(pool, type_="work_done", retry_fn=self.random_worker):
                node_weight = self.wm.get_info(worker_id)["n_samples"]
                weighted_sum += data*node_weight
                total_weight += node_weight
            self.ml.set_weights(weighted_sum/total_weight)
            self.validate(epoch, self.x_val, self.y_val)
            stop = self.early_stop() or epoch == self.epochs
            if stop:
                self.wm.send_n(self.wm.get_all_workers(), type_=WorkerManager.EXIT_TYPE)
                break

    
    def on_work(self, node_id, weights):
        self.ml.set_weights(weights)
        self.ml.train(self.epochs)
        self.wm.send(WorkerManager.MASTER_ID, self.ml.get_weights(), "work_done")

