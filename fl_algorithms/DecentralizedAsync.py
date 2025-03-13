
from my_builtins.FederatedABC import FederatedABC
from my_builtins.WorkerManager import WorkerManager

class Task:
    WEIGHTS = 0
    WORK = 1
    WORK_DONE = 2
    WEIGHTS_DIFF = 3

class DecentralizedSync(FederatedABC):


    def __init__(self, *, 
        local_epochs: int = 3,
        alpha: float = 0.3,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.local_epochs = local_epochs
        self.running = True


    def setup(self):
        self.ml.compile_model()
        if self.is_master:
            self.ml.load_data("val")
            self.wm.on_new_worker = self.on_new_worker
        else:
            self.ml.load_data("train")
        self.wm.set_callbacks(
            (Task.WEIGHTS, self.on_weights),
            (Task.WORK, self.on_work),
            (Task.WEIGHTS_DIFF, self.on_weights_diff)
        )


    def get_worker_info(self) -> dict:
        return {
            "n_samples": self.ml.n_samples,
        }


    def master_loop(self):
        ...
        # for epoch in range(1, self.epochs+1):
        #     self.wm.wait_for_workers(self.min_workers)
        #     pool = self.wm.get_subpool(self.min_workers, self.random_pool)
        #     self.wm.send_n(
        #         workers = pool, 
        #         payload = None,
        #         type_ = Task.WORK
        #     )
        #     for worker_id, payload in self.wm.recv_n(
        #         workers = pool, 
        #         type_ = Task.WORK_DONE,
        #         retry_fn = self.retry_fn
        #     ):
        #         # TODO do something with weights
        #         weights_diff = None
        #         self.wm.send(
        #             node_id = worker_id,
        #             payload = weights_diff,
        #             type_ = Task.WEIGHTS_DIFF
        #         )
        #     self.validate(epoch, split="val", verbose=True)
        #     stop = self.early_stop() or epoch == self.epochs
        #     if stop:
        #         self.wm.send_n(
        #             workers = self.wm.get_all_workers(), 
        #             type_ = WorkerManager.EXIT_TYPE
        #         )
        #         break


    # def retry_fn(self, worker_info, responses):
    #     while True:
    #         ids = set(worker_info.keys()) - set(k for k, v in responses.items() if not v)
    #         if len(ids) == 0:
    #             self.wm.loop_once()
    #             continue
    #         new_worker = random.choice(list(ids))
    #         return new_worker, None, Task.WORK


    def on_new_worker(self, worker_id, info):
        self.wm.send(
            node_id = worker_id,
            payload = self.ml.get_weights(),
            type_ = Task.WEIGHTS
        )


    def on_weights(self, sender_id, payload):
        self.ml.set_weights(payload)


    def on_work(self, sender_id, payload):
        self.ml.train(self.local_epochs)
        self.wm.send(
            node_id = WorkerManager.MASTER_ID, 
            payload = self.ml.get_weights(), 
            type_ = Task.WORK_DONE
        )

    
    def on_weights_diff(self, sender_id, weights_diff):
        # TODO update weights
        new_weights =  None
        self.ml.set_weights(new_weights)


    