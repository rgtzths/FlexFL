import sys
sys.path.append(".")

from dotenv import load_dotenv
load_dotenv()

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 

# datasets
from Datasets.IOT_DNL import IOT_DNL

# ML
from ML.Torch import Torch as MLtorch
from ML.Tensorflow import Tensorflow as MLtf

# FL
from FL.CentralizedSync import CentralizedSync
from FL.CentralizesAsync import CentralizedAsync
from FL.DecentralizedAsync import DecentralizedAsync
from FL.DecentralizedSync import DecentralizedSync

# XAI


os.environ['TF_CPP_MIN_LOG_LEVEL'] = '0'
print("Config loaded\n")


DATASETS = {
    'IOT_DNL': IOT_DNL
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
