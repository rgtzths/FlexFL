from abc import ABC
from typing import Any

from flexfl.builtins.DatasetABC import DatasetABC

class NeuralNetworkABC(ABC):
    """
    Implement a function "{ml_prefix}_model" for each ml framework (do the imports inside the function)

    Required classification output space per backend: `keras_model` / `tf_model`
    MUST end in a Softmax layer (their `scc` loss expects probabilities), while
    `torch_model` MUST NOT append `nn.Softmax` (its `scc` loss, `CrossEntropyLoss`,
    expects raw logits and applies log-softmax internally). Adding a Softmax to the
    torch classification path re-introduces a double-softmax that degrades training.
    """

    def __init__(self, **kwargs) -> None:
        return
    

    def get_model(self, ml_prefix: str, dataset: DatasetABC) -> Any:
        input_shape = tuple(dataset.metadata['input_shape'])
        output_size = dataset.metadata['output_size']
        is_classification = dataset.is_classification
        return getattr(self, f"{ml_prefix}_model")(dataset.name, input_shape, output_size, is_classification)
