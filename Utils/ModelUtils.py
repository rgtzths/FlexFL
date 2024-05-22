
class ModelUtils:
    """
    Methods to implement in the child class:
    - {ml}_model(self, input_shape, classes=None)
    """

    def __init__(self,
        **kwargs
    ):
        return


    def get_model(self, ml, dataset):
        input_shape = tuple(dataset.metadata['input_shape'])
        classes = dataset.metadata.get('classes', None)
        return getattr(self, f"{ml}_model")(input_shape, classes)

