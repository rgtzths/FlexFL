import pprint
from pathlib import Path
from abc import ABC, abstractmethod
from permetrics import RegressionMetric, ClassificationMetric
import numpy as np
from time import time
from collections import deque

from Utils.MLUtils import MLUtils
from Utils.CommUtils import CommUtils

CLASSIFICATIONS = {'scc'}
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


class FLUtils(ABC):

    def __init__(self, *, 
        ml: MLUtils,
        comm: CommUtils,
        epochs = 10,
        max_score = 0.99,
        patience = 5,
        delta = 0.01,
        main_metric: str = None, # MCC for classification, SMAPE for regression
        seed = 42,
        **kwargs
    ):
        self.ml = ml
        self.comm = comm
        self.epochs = epochs
        self.max_score = max_score
        self.patience = patience
        self.delta = delta
        self.stop = False
        self.is_classification = self.ml.loss_name in CLASSIFICATIONS
        self.metrics  = self.get_metrics(main_metric) # first metric used for early stopping
        self.buffer = deque(maxlen=patience)
        self.compare_score = None
        self.best_score = None
        self.best_weights = None
        self.last_time = 0

        self.base_path = (
            'Results/' +
            f'{self.ml.dataset.__class__.__name__}/' +  # dataset
            f'{self.__class__.__name__}/' +             # fl
            f'{self.comm.__class__.__name__}/' +        # comm
            f'{self.comm.n_workers}/' +                 # n_workers
            f'{self.ml.prefix}/' +                      # ml prefix
            f'{seed}/' +                                # seed
            f'{self.ml.optimizer_name}/' +              # optimizer
            f'{self.ml.batch_size}/' +                  # batch_size
            f'{self.epochs}'                            # epochs
        )


    @abstractmethod
    def setup(self) -> None:
        """
        Setup the FL environment
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


    def get_metrics(self, main_metric: str) -> list[str]:
        """
        Get the metrics to be used for validation

        Parameters:
            main_metric (str): the main metric to be used for early stopping

        Returns:
            list[str]: the metrics to be used for validation and early stopping, where the first metric is the main metric
        """

        all_metrics, self.evaluator = (
            (METRICS['classification'], ClassificationMetric) 
            if self.is_classification else
            (METRICS['regression'], RegressionMetric)
        )
        if main_metric is None:
            return all_metrics
        if main_metric in all_metrics:
            return [main_metric] + [all_metrics.remove(main_metric)]
        raise ValueError(f"main_metric must be one of {all_metrics}")


    def create_base_path(self) -> None:
        """
        Create the base path for the results in the master node
        """
        if self.comm.is_master():
            Path(self.base_path).mkdir(parents=True, exist_ok=True)


    def run(self) -> None:
        """
        Run the Federated Learning
        """
        self.create_base_path()
        self.setup()
        # TODO: do something with the time
        self.last_time = time()
        if self.comm.is_master():
            _, self.y_val = self.ml.load_data('val')
            self.master_train()
        else:
            self.ml.load_worker_data(self.comm.worker_id, self.comm.n_workers)
            self.worker_train()


    def validate(self, epoch: int) -> float:
        """
        Validate the model

        Parameters:
            epoch (int): the current epoch

        Returns:
            float: the new score
        """
        
        preds = self.ml.predict(self.y_val)
        if self.is_classification:
            preds = np.argmax(preds, axis=1)
        metrics = self.evaluator(self.y_val, preds).get_metrics_by_list_names(self.metrics)
        new_time = time()
        print(f"Epoch {epoch}/{self.epochs} - Time: {new_time - self.last_time:.2f}s")
        self.last_time = new_time
        print("Validation Metrics:")
        for metric in metrics:
            print(f"{metric}: {metrics[metric]:.4f}", end=', ')
        print()
        new_score = metrics[self.metrics[0]]
        if (
            self.best_score is None or
            (self.is_classification and new_score > self.best_score) or
            (not self.is_classification and new_score < self.best_score)
        ):
            self.best_score = new_score
            self.best_weights = self.ml.get_weights()
        return new_score


    def early_stop(self, new_score: float) -> bool:
        """
        Check if the training should stop early

        Parameters:
            new_score (float): the new score

        Returns:
            bool: True if the training should stop early and False otherwise
        """

        if len(self.buffer) < self.patience:
            self.buffer.append(new_score)
            return False
        
        old_score = self.buffer.popleft()
        if (
            self.compare_score is None or
            (self.is_classification and old_score > self.compare_score) or
            (not self.is_classification and old_score < self.compare_score)
        ):
            self.compare_score = old_score
        
        self.buffer.append(new_score)
        if self.is_classification:
            return not any(score > self.compare_score + self.delta for score in self.buffer)
        else:
            return not any(score < self.compare_score - self.delta for score in self.buffer)
            

    def __str__(self):
        return pprint.pformat(vars(self))