import torch

from Utils.MLUtils import MLUtils

OPTIMIZERS = {}

LOSSES = {}

class Torch(MLUtils):
    
    def init(self):
        self.prefix = 'torch'