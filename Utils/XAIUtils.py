

class XAIUtils():
    """
    Methods to implement in the child class:
    - run_tf(self)
    - run_torch(self)
    """

    def __init__(self, *, 
        dataset,
        ml = 'tf',
        file_path = None,
        **kwargs
    ):
        self.dataset = dataset
        self.ml = ml
        self.file_path
        self.model = getattr(self, f"load_{ml}")()


    def load_tf(self):
        ...


    def load_torch(self):
        ...


    def run(self):
        getattr(self, f"run_{self.ml}")()