
from Utils.FLUtils import FLUtils

class DecentralizedSync(FLUtils):
    
    def __init__(self, *,
        local_epochs, 
        **kwargs
    ):
        super().__init__(**kwargs)
        self.local_epochs = local_epochs

    def run(self):
        ...