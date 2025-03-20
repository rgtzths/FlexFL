from dotenv import load_dotenv
import os
load_dotenv()

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'


from flexfl.datasets.IOT_DNL import IOT_DNL
from flexfl.neural_nets.IOT_DNL import IOT_DNL as IOT_DNL_NN
from flexfl.msg_layers.Raw import Raw
from flexfl.ml_fw.TensorFlow import TensorFlow
from flexfl.comms.MPI import MPI
from flexfl.fl_algos.DecentralizedAsync import DecentralizedAsync
from flexfl.builtins.WorkerManager import WorkerManager


f = DecentralizedAsync(
    ml=TensorFlow(
        nn=IOT_DNL_NN(),
        dataset=IOT_DNL(),
    ),
    wm=WorkerManager(
        c=MPI(),
        m=Raw()
    ),
    min_workers=4,
    all_args={}
)

f.run()
