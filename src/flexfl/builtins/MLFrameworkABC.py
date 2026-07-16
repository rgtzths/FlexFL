from abc import ABC, abstractmethod
import numpy as np
import random
from typing import Any

from flexfl.builtins.DatasetABC import DatasetABC
from flexfl.builtins.NeuralNetworkABC import NeuralNetworkABC


CLASSIFICATION_LOSSES = {"scc"}
REGRESSION_LOSSES = {"mse", "mae", "mape"}


class MLFrameworkABC(ABC):

    def __init__(self, *,
        nn: NeuralNetworkABC,
        dataset: DatasetABC,
        optimizer: str = "adam",
        loss: str | None = None,
        learning_rate: float = 0.001,
        batch_size: int = 1024,
        seed: int = 42,
        use_gpu: bool = False,
        **kwargs
    ) -> None:
        self.dataset = dataset
        self.optimizer_name = optimizer
        self.loss_name = self.resolve_loss(loss, dataset.is_classification)
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


    @staticmethod
    def resolve_loss(loss_name: str | None, is_classification: bool) -> str:
        """
        Derive the training loss from the dataset task when not given, and
        reject an explicit loss that contradicts the task.
        """
        allowed = CLASSIFICATION_LOSSES if is_classification else REGRESSION_LOSSES
        if loss_name is None:
            return "scc" if is_classification else "mse"
        if loss_name not in allowed:
            task = "classification" if is_classification else "regression"
            raise SystemExit(
                f"Loss '{loss_name}' is not valid for a {task} dataset; "
                f"choose one of {sorted(allowed)} (or omit --loss to use the default)."
            )
        return loss_name


    @staticmethod
    def _check_flat_length(expected: int, got: int, label: str) -> None:
        if expected != got:
            raise ValueError(
                f"{label}: flat vector length {got} does not match model layout "
                f"({expected}); weight/gradient layouts have diverged."
            )


    @classmethod
    def supports_gradients(cls, backend: str | None = None) -> bool:
        """
        Whether this framework implements calculate_gradients/apply_gradients
        (server-side gradient aggregation) for the given backend. Frameworks that
        cannot must override this so cli/fl.py can reject a gradient-based FL
        algorithm before any worker connects. Default: supported.
        """
        return True


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
        Predict the data. `data` is the backend-native feature container
        stored by `load_data` (a batched `tf.data.Dataset` for Keras/TensorFlow,
        a `torch.Tensor` for PyTorch).
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