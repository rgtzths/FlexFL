from abc import ABC, abstractmethod
import numpy as np
import random
from typing import Any

from flexfl.builtins.DatasetABC import DatasetABC
from flexfl.builtins.NeuralNetworkABC import NeuralNetworkABC


class MLFrameworkABC(ABC):

    def __init__(self, *,
        nn: NeuralNetworkABC,
        dataset: DatasetABC,
        optimizer: str = "adam",
        loss: str = "scc",
        learning_rate: float = 0.001,
        batch_size: int = 1024,
        seed: int = 42,
        use_gpu: bool = False,
        **kwargs
    ) -> None:
        self.dataset = dataset
        self.optimizer_name = optimizer
        self.loss_name = loss
        self.learning_rate = learning_rate
        self.batch_size = batch_size
        self.seed = seed
        self.use_gpu = use_gpu
        random.seed(seed)
        np.random.seed(seed)
        self.set_seed(seed)
        self.model = nn.get_model(self.prefix, dataset)
        self.n_samples = None
        self.setup()


    @property
    @abstractmethod
    def prefix(self) -> str:
        """
        Returns the prefix for the ml framework
        """
        pass


    @abstractmethod
    def set_seed(self, seed: int) -> None:
        """
        Set the seed
        """
        pass


    @abstractmethod
    def setup(self) -> None:
        """
        Setup the ml environment, e.g. loss, optimizer
        """
        pass


    @abstractmethod
    def load_data(self, split: str) -> None:
        """
        Load the split data and set n_samples
        """
        pass


    @abstractmethod
    def get_weights(self) -> np.ndarray:
        """
        Get the model weights
        """
        pass


    @abstractmethod
    def set_weights(self, weights: np.ndarray) -> None:
        """
        Set the model weights
        """
        pass


    @abstractmethod
    def calculate_gradients(self) -> np.ndarray:
        """
        Calculate the model gradients
        """
        pass


    @abstractmethod
    def apply_gradients(self, gradients: np.ndarray) -> None:
        """
        Set the model gradients
        """
        pass


    @abstractmethod
    def train(self, epochs: int, verbose=False) -> None:
        """
        Train the model
        """
        pass


    @abstractmethod
    def predict(self, data: Any) -> np.ndarray:
        """
        Predict the data
        """
        pass


    @abstractmethod
    def calculate_loss(self, y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """
        Calculate the loss
        """
        pass


    @abstractmethod
    def save_model(self, path: str) -> None:
        """
        Save the model
        """
        pass


    @abstractmethod
    def load_model(self, path: str) -> None:
        """
        Load the model
        """
        pass