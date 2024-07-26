import sys
sys.path.append(".")

from dotenv import load_dotenv
load_dotenv()

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'

# utils
from Utils.DatasetUtils import DatasetUtils
from Utils.MLUtils import MLUtils
from Utils.FLUtils import FLUtils
from Utils.ModelUtils import ModelUtils
from Utils.XAIUtils import XAIUtils

# datasets
from Datasets.IOT_DNL import IOT_DNL
from Datasets.MNIST import MNIST
from Datasets.FASHION import FASHION
from Datasets.CIFAR10 import CIFAR10
from Datasets.UNSW import UNSW
from Datasets.Slicing5G import Slicing5G

# models
from Models.IOT_DNL_M1 import IOT_DNL_M1
from Models.UNSW_M1 import UNSW_M1

# ML
from ML.Torch import Torch as MLtorch
from ML.Tensorflow import Tensorflow as MLtf

# Comm
from Comm.MPI import MPI as CommMPI

# FL
from FL.CentralizesAsync import CentralizedAsync
from FL.CentralizedSync import CentralizedSync
from FL.DecentralizedAsync import DecentralizedAsync
from FL.DecentralizedSync import DecentralizedSync

# XAI


# update tf logging level
import tensorflow as tf
tf.get_logger().setLevel('WARN')

print("Config loaded\n")


UTILS = {
    'dataset': DatasetUtils,
    'model': ModelUtils,
    'ml': MLUtils,
    'fl': FLUtils,
    'xai': XAIUtils
}

DATASETS = {
    'IOT_DNL': IOT_DNL,
    'MNIST': MNIST,
    'FASHION': FASHION,
    'CIFAR10': CIFAR10,
    'UNSW': UNSW,
    'Slicing5G': Slicing5G
}

MODELS = {
    'IOT_DNL': IOT_DNL_M1,
    'UNSW': UNSW_M1
}

ML = {
    'torch': MLtorch,
    'tf': MLtf
}

COMM = {
    'mpi': CommMPI
}

FL = {
    1: CentralizedAsync,
    2: CentralizedSync,
    3: DecentralizedAsync,
    4: DecentralizedSync
}

XAI = {

}
