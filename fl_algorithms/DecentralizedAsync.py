from enum import IntEnum, auto

from my_builtins.FederatedABC import FederatedABC
from my_builtins.WorkerManager import WorkerManager

class Task(IntEnum):
    WORK = auto()
    WORK_DONE = auto()


class DecentralizedSync(FederatedABC):


    def __init__(self, *, 
        local_epochs: int = 3,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.local_epochs = local_epochs


    def setup(self):
        self.ml.compile_model()
        if self.is_master:
            self.x_val, self.y_val = self.ml.load_data("val")
        else:
            self.ml.load_worker_data(self.id, 8)
        self.wm.set_callbacks(
            (Task.WORK, self.on_work)
        )


    def get_worker_info(self) -> dict:
        return {
            "n_samples": self.ml.n_samples,
        }