from time import time
from sklearn.metrics import accuracy_score, f1_score, matthews_corrcoef

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
        self.base_path += f'/{self.local_epochs}/{self.alpha}'



    def setup(self):

        if self.comm.is_master():
            self.node_weights = [0] * self.comm.n_workers
            _, self.y_val = self.ml.load_data('val')
            
            for _ in range(self.comm.n_workers):
                worker_id, n_samples = self.comm.recv_worker()
                self.node_weights[worker_id] = n_samples
            self.node_weights = [n_samples / sum(self.node_weights) for n_samples in self.node_weights]

            self.comm.send_workers(self.ml.get_weights())
                
        else:
            self.ml.load_worker_data(self.comm.worker_id, self.comm.n_workers)
            self.comm.send_master(self.ml.dataset.n_samples)

            weights = self.comm.recv_master()
            self.ml.set_weights(weights)



    def validate(self, epoch):
        preds = self.ml.predict('val')
        val_f1 = f1_score(self.y_val, preds, average='macro')
        val_mcc = matthews_corrcoef(self.y_val, preds)
        val_acc = accuracy_score(self.y_val, preds)

        print(f'Val F1: {val_f1:.4f}, Val MCC: {val_mcc:.4f}, Val Acc: {val_acc:.4f}')

        self.patience_buffer = self.patience_buffer[1:] + [val_mcc]
        self.all_results.append(val_mcc)

        p_stop = True
        max_mcc = max(self.all_results[:-self.patience], default=0)
        max_buffer = max(self.patience_buffer, default=0)
        if max_mcc + self.delta > max_buffer:
            p_stop = False

        if (val_mcc > self.max_score or p_stop) and epoch//self.comm.n_workers+1 > 10:
            self.stop = True



    def master_train(self):
        exited_workers = 0

        for epoch in range(self.epochs*self.comm.n_workers):
            epoch_start = time()
            if exited_workers == self.comm.n_workers:
                break
            if epoch % self.comm.n_workers == 0:
                print(f'Epoch {epoch//self.comm.n_workers + 1}, Time: {time() - epoch_start:.2f}s')

            worker_id, weights = self.comm.recv_worker()
            local_weights = self.ml.get_weights()

            weight_diffs = [ 
                (weight - local_weights[idx])*self.alpha*self.node_weights[worker_id]
                for idx, weight in enumerate(weights)
            ]
            local_weights = [
                local_weights[idx] + weight
                for idx, weight in enumerate(weight_diffs)
            ]

            self.ml.set_weights(local_weights)

            self.comm.send_worker(worker_id, weight_diffs)

            if self.stop:
                exited_workers +=1
            
            if epoch % self.comm.n_workers == self.comm.n_workers-1:
                self.validate(epoch)
            self.comm.send_worker(worker_id, self.stop)
  


    def worker_train(self):
        
        for _ in range(self.epochs):
            self.ml.train(self.local_epochs)

            weights = self.ml.get_weights()
            self.comm.send_master(weights)
            weight_diffs = self.comm.recv_master()
            new_weights = [
                weight - weight_diffs[idx]
                for idx, weight in enumerate(weights)
            ]
            self.ml.set_weights(new_weights)
            stop = self.comm.recv_master()
            if stop:
                break

    

    def run(self):
        
        self.create_base_path()
        self.ml.compile_model()

        self.setup()
        
        if self.comm.is_master():
            self.master_train()
        else:
            self.worker_train()

        

        