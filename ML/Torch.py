import torch

from Utils.MLUtils import MLUtils

OPTIMIZERS = {}

LOSSES = {}

class Torch(MLUtils):
    
    def setup(self):
        self.prefix = 'torch'