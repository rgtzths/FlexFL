from Utils.FLUtils import FLUtils

class CentralizedAsync(FLUtils):


    def setup(self):
        ...


    def master_train(self):
        ...
    
    
    def worker_train(self):
        stop = False
        while not stop:
            grads = self.ml.get_gradients()
            self.comm.send_master(grads)
            weights = self.comm.recv_master()
            self.ml.set_weights(weights)
            stop = self.comm.recv_master()
