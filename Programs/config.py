import sys
sys.path.append(".")

from dotenv import load_dotenv
load_dotenv()

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 

# datasets
from Datasets.IOT_DNL import IOT_DNL
from Datasets.MNIST import MNIST
from Datasets.FASHION import FASHION
from Datasets.CIFAR10 import CIFAR10

# ML
from ML.Torch import Torch as MLtorch
from ML.Tensorflow import Tensorflow as MLtf

# FL
from FL.CentralizedSync import CentralizedSync
from FL.CentralizesAsync import CentralizedAsync
from FL.DecentralizedAsync import DecentralizedAsync
from FL.DecentralizedSync import DecentralizedSync

# XAI


# update tf logging level
import tensorflow as tf
tf.get_logger().setLevel('WARN')

print("Config loaded\n")


DATASETS = {
    'IOT_DNL': IOT_DNL,
    'MNIST': MNIST,
    'FASHION': FASHION,
    'CIFAR10': CIFAR10
}

ML = {
    'torch': MLtorch,
    'tf': MLtf
}

FL = {
    1: CentralizedSync,
    2: CentralizedAsync,
    3: DecentralizedSync,
    4: DecentralizedAsync
}

XAI = {

}
