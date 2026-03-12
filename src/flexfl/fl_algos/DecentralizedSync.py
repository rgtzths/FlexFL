import time

from flexfl.builtins.FederatedABC import FederatedABC
from flexfl.builtins.WorkerManager import WorkerManager
from flexfl.builtins.Logger import Logger

class Task:
    WORK = 0
    WORK_DONE = 1

class DecentralizedSync(FederatedABC):

    def __init__(self, *, 
        local_epochs: int = 3,
        epoch_threshold: float = 0.5,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.local_epochs = local_epochs
        self.epoch_threshold = epoch_threshold


    def setup(self):
        if self.is_master:
            self.ml.load_data("val")
        else:
            self.ml.load_data("train")
        self.wm.set_callbacks(
            (Task.WORK, self.on_work)
        )


    def get_worker_info(self) -> dict:
        return {
            "n_samples": self.ml.n_samples,
        }


    def master_loop(self):
        weights = self.ml.get_weights()
        self.wm.wait_for_workers(self.min_workers)
        print("Starting...")
        Logger.log(Logger.START)
        self.epoch_start = time.time()
        epoch = 0
        stop = False
        while True:
            self.wm.wait_for_workers(self.min_workers)
            pool = self.wm.get_subpool(self.min_workers, self.subpool_fn)
            self.wm.send_n(
                workers = pool, 
                payload = weights,
                type_ = Task.WORK
            )
            if epoch > 0:
                self.ml.set_weights(weights)
                self.validate(epoch, split="val", verbose=True)
                stop = self.early_stop() or epoch == self.epochs
                if stop:
                    Logger.log(Logger.END)
            weighted_sum = 0
            total_weight = 0
            for i, (worker_id, data) in enumerate(self.wm.recv_n(
                workers = pool, 
                type_ = Task.WORK_DONE,
            )):
                if stop:
                    continue
                node_weight = self.wm.get_info(worker_id)["n_samples"]
                weighted_sum += data*node_weight
                total_weight += node_weight
            if stop:
                break
            if i+1 < int(self.min_workers*self.epoch_threshold):
                continue
            epoch += 1
            weights = weighted_sum/total_weight
        self.wm.end()


    def subpool_fn(self, size, worker_info):
        return self.round_robin_pool(size, set(worker_info.keys()))

    
    def on_work(self, sender_id, weights):
        Logger.log(Logger.WORKING_START)
        self.ml.set_weights(weights)
        self.ml.train(self.local_epochs)
        new_weights = self.ml.get_weights()
        Logger.log(Logger.WORKING_END)
        self.wm.send(
            node_id = WorkerManager.MASTER_ID, 
            payload = new_weights, 
            type_ = Task.WORK_DONE
        )

