
from Utils.FLUtils import FLUtils

class DecentralizedAsync(FLUtils):
    
    def __init__(self, *,
        local_epochs, 
        alpha, 
        **kwargs
    ):
        super().__init__(**kwargs)
        self.local_epochs = local_epochs
        self.alpha = alpha

    
    def run(self):
        ...