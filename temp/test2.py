from dotenv import load_dotenv
import os
load_dotenv()

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'


from flx.datasets.IOT_DNL import IOT_DNL
from flx.neural_nets.IOT_DNL import IOT_DNL as IOT_DNL_NN
from flx.msg_layers.Raw import Raw
from flx.ml_fw.TensorFlow import TensorFlow
from flx.comms.MPI import MPI
from flx.fl_algos.DecentralizedAsync import DecentralizedAsync
from flx.builtins.WorkerManager import WorkerManager


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
