from abc import ABC
from typing import Any

from flexfl.builtins.DatasetABC import DatasetABC

class NeuralNetworkABC(ABC):
    """
    Implement a function "{ml_prefix}_model" for each ml framework (do the imports inside the function)
    """

    def __init__(self, **kwargs) -> None:
        return
    

    def get_model(self, ml_prefix: str, dataset: DatasetABC) -> Any:
        input_shape = tuple(dataset.metadata['input_shape'])
        output_size = dataset.metadata['output_size']
        is_classification = dataset.is_classification
        return getattr(self, f"{ml_prefix}_model")(input_shape, output_size, is_classification)