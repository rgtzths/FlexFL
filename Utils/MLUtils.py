import pprint
from abc import ABC, abstractmethod

from Utils.ModelUtils import ModelUtils
from Utils.DatasetUtils import DatasetUtils

class MLUtils(ABC):
    """
    Functions to implement in the child class:
    - init(self)
    - load_data(self, split)
    - load_worker_data(self, worker_id, num_workers)
    - get_weights(self)
    - set_weights(self, weights)
    - get_gradients(self)
    - apply_gradients(self, gradients)
    - train(self, epochs)
    - predict(self, data)
    - save_model(self, path)
    - load_model(self, path)
    """

    def __init__(self, *,
        model: ModelUtils,
        dataset: DatasetUtils,
        optimizer = 'adam',
        loss = 'scc',
        learning_rate = 0.001,
        batch_size = 1024,
        **kwargs
    ):
        self.prefix = None
        self.dataset = dataset
        self.optimizer = optimizer
        self.optimizer_name = optimizer
        self.loss = loss
        self.loss_name = loss
        self.learning_rate = learning_rate
        self.batch_size = int(batch_size)
        self.setup()
        self.model = model.get_model(self.prefix, self.dataset)
        self.n_samples = None


    @abstractmethod
    def setup(self):
        """
        Setup the ML environment, e.g. prefix, loss, optimizer
        """
        pass


    @abstractmethod
    def load_data(self, split: str) -> tuple[any, any]:
        """
        Load the data for the given split, set the data attribute

        Parameters:
            split (str): 'train', 'val', 'test'

        Returns:
            tuple (any, any): the dataset original data
        """
        pass


    @abstractmethod
    def load_worker_data(self, worker_id: int, num_workers: int) -> tuple[any, any]:
        """
        Load the data for the given worker, set the data attribute and an iterator for the data

        Parameters:
            worker_id (int): the worker id
            num_workers (int): the number of workers

        Returns:
            tuple (any, any): the worker data
        """
        pass


    @abstractmethod
    def compile_model(self) -> None:
        """
        Compile the model
        """
        pass


    @abstractmethod
    def get_weights(self) -> any:
        """
        Get the model weights

        Returns:
            any: the model weights
        """
        pass


    @abstractmethod
    def set_weights(self, weights: any) -> None:
        """
        Set the model weights

        Parameters:
            weights (any): the model weights
        """
        pass


    @abstractmethod
    def get_gradients(self) -> any:
        """
        Get the model gradients

        Returns:
            any: the model gradients
        """
        pass


    @abstractmethod
    def apply_gradients(self, gradients: any) -> None:
        """
        Apply the model gradients

        Parameters:
            gradients (any): the model gradients
        """
        pass


    @abstractmethod
    def train(self, epochs: int) -> None:
        """
        Train the model

        Parameters:
            epochs (int): the number of epochs
        """
        pass


    @abstractmethod
    def predict(self, data: any) -> any:
        """
        Predict the data

        Parameters:
            data (any): the data to predict

        Returns:
            any: the predictions
        """
        pass


    @abstractmethod
    def save_model(self, path: str) -> None:
        """
        Save the model

        Parameters:
            path (str): the path to save the model
        """
        pass


    @abstractmethod
    def load_model(self, path: str) -> None:
        """
        Load the model

        Parameters:
            path (str): the path to load the model
        """
        pass


    def __str__(self):
        return pprint.pformat(vars(self))