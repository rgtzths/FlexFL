import torch

from ML.MLUtils import MLUtils

OPTIMIZERS = {}

LOSSES = {}

class Torch(MLUtils):
    
    def __init__(self,
        optimizer,
        loss,
        learning_rate,
        **kwargs
    ):
        prefix = 'torch'
        # TODO - Add torch optimizers and losses
        # optimizer = OPTIMIZERS[optimizer](learning_rate=learning_rate)
        # loss = LOSSES[loss]()
        super().__init__(prefix, optimizer, loss, **kwargs)