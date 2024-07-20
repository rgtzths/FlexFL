
from Utils.FLUtils import FLUtils

class DecentralizedAsync(FLUtils):
    
    def __init__(self, *,
        local_epochs = 3,
        alpha = 0.2,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.local_epochs = local_epochs
        self.alpha = alpha
        self.base_path += f'_{self.local_epochs}_{self.alpha}'


    def setup(self):

        if self.comm.is_master():
            self.node_weights = [0] * self.comm.n_workers
            self.ml.load_data('val')
            self.comm.set_buffer(self.ml.dataset.n_samples)
            
            for _ in range(self.comm.n_workers):
                worker_id, n_samples = self.comm.recv_worker()
                print(f"Worker {worker_id} has {n_samples} samples")
                self.node_weights[worker_id] = n_samples
            self.node_weights = [n_samples / sum(self.node_weights) for n_samples in self.node_weights]
                
        else:
            self.ml.load_worker_data(self.comm.worker_id, self.comm.n_workers)
            self.comm.set_buffer(self.ml.dataset.n_samples)
            self.comm.send_master()

    
    def run(self):
        
        self.create_base_path()
        self.ml.compile_model()

        self.setup()

        if self.comm.is_master():
            print("\n\n\n")
            print(self.node_weights)

        