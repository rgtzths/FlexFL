from abc import ABC, abstractmethod
from permetrics import RegressionMetric, ClassificationMetric
from collections import deque
import json
from pathlib import Path
from time import time

from my_builtins.WorkerManager import WorkerManager
from my_builtins.MLFrameworkABC import MLFrameworkABC

RESULTS_FOLDER = "results"

METRICS = {
    'classification': [
        'MCC',
        'AS',
        'F1S'
    ],
    'regression': [
        'SMAPE',
        'MSE',
        'MAE'
    ]
}

class FederatedABC(ABC):

    def __init__(self, *,
        ml: MLFrameworkABC,
        wm: WorkerManager,
        all_args: dict,
        epochs: int = 10,
        target_score: float = None,
        patience: int = 5,
        delta: float = 0.01,
        main_metric: str = None,
        **kwargs
    ) -> None:
        self.ml = ml
        self.wm = wm
        self.all_args = all_args
        self.epochs = epochs
        self.target_score = target_score
        self.patience = patience
        self.delta = delta
        self.main_metric = main_metric
        
        self.buffer = deque(maxlen=patience)
        self.compare_score = None
        self.best_score = None
        self.best_weights = None
        self.last_time = 0

        self.setup_metrics()
        self.setup_nodes()


    @abstractmethod
    def master_setup(self) -> None:
        """
        Setup the master environment
        """
        pass


    @abstractmethod
    def worker_setup(self) -> None:
        """
        Setup the worker environment
        """
        pass


    @abstractmethod
    def master_train(self) -> None:
        """
        Master train loop
        """
        pass


    @abstractmethod
    def worker_train(self) -> None:
        """
        Worker train loop
        """
        pass


    def setup_metrics(self):
        self.is_classification = self.ml.dataset.is_classification

        if self.main_metric is None:
            self.main_metric = METRICS['classification'][0] if self.is_classification else METRICS['regression'][0]
        if self.target_score is None:
            self.target_score = 1.0 if self.is_classification else 0.0
        
        all_metrics, self.evaluator = (
            (METRICS['classification'], ClassificationMetric) 
            if self.is_classification else
            (METRICS['regression'], RegressionMetric)
        )
        assert self.main_metric in all_metrics, f"main_metric must be one of {all_metrics}"
        all_metrics.remove(self.main_metric)
        self.metrics = [self.main_metric] + all_metrics

    
    def setup_nodes(self):
        self.is_master = self.wm.c.id == 0
        self.id = self.wm.c.id
        self.base_path = f"{RESULTS_FOLDER}/{self.wm.c.start_time.strftime('%Y-%m-%d_%H:%M:%S')}"
        Path(self.base_path).mkdir(parents=True, exist_ok=True)
        with open(f"{self.base_path}/args.json", "w") as f:
            json.dump(self.all_args, f, indent=4)
        # TODO setup logger


    def run(self):
        start = time()
        if self.is_master:
            self.master_setup()
        else:
            self.worker_setup()
        setup_time = time() - start
        self.last_time = time()
        if self.is_master:
            self.master_train()
        else:
            self.worker_train()
        self.end()


    def end(self):
        if self.is_master:
            self.ml.set_weights(self.best_weights)
            self.ml.save_model(f"{self.base_path}/model")
        # TODO gather logs
        self.wm.c.close()