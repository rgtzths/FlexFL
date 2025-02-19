from abc import ABC, abstractmethod

class NeuralNetworkABC(ABC):
    """
    Implement a function "{ml_prefix}_model" for each ml framework (do the imports inside the function)
    """

    def __init__(self, **kwargs) -> None:
        return
    

    def get_model(self, ml_prefix, dataset) -> any:
        input_shape = tuple(dataset.metadata['input_shape'])
        output_shape = tuple(dataset.metadata['output_shape'])
        return getattr(self, f"{ml_prefix}_model")(input_shape, output_shape)