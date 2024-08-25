from sklearn.metrics import accuracy_score, f1_score, matthews_corrcoef

from Utils.FLUtils import FLUtils

class CentralizedAsync(FLUtils):


    def setup(self):

        if self.comm.is_master():
            self.node_weights = [0] * self.comm.n_workers
            _, self.y_val = self.ml.load_data('val')
            
            for _ in range(self.comm.n_workers):
                worker_id, n_batches = self.comm.recv_worker()
                self.node_weights[worker_id] = n_batches

            sum_n_batches = sum(self.node_weights)
            self.total_n_batches = max(self.node_weights)
            self.total_batches = self.total_n_batches * self.epochs
            self.node_weights = [n_batches / sum_n_batches for n_batches in self.node_weights]

            self.comm.send_workers(self.ml.get_weights())
                
        else:
            self.ml.load_worker_data(self.comm.worker_id, self.comm.n_workers)
            n_batches = self.ml.dataset.n_samples // self.ml.batch_size
            self.comm.send_master(n_batches)

            weights = self.comm.recv_master()
            self.ml.set_weights(weights)



    def validate(self, epoch):
        preds = self.ml.predict('val')
        val_f1 = f1_score(self.y_val, preds, average='macro')
        val_mcc = matthews_corrcoef(self.y_val, preds)
        val_acc = accuracy_score(self.y_val, preds)

        print(f"Epoch {epoch+1}/{self.epochs}")
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

        if epoch == self.epochs-1:
            self.stop = True


    def master_train(self):
        exited_workers = 0
        # TODO: Implement tag system
        latest_tag = 0

        for batch in range(self.total_batches):
            
            worker_id, grads = self.comm.recv_worker()

            grads = [grad * self.node_weights[worker_id] for grad in grads]
            self.ml.apply_gradients(grads)
            self.comm.send_worker(worker_id, self.ml.get_weights())

            if batch % self.total_n_batches == 0:
                self.validate(batch // self.total_n_batches)
            
            self.comm.send_worker(worker_id, self.stop)
            if self.stop:
                exited_workers += 1
                if exited_workers == self.comm.n_workers:
                    break

    
    
    def worker_train(self):
        while not self.stop:
            grads = self.ml.get_gradients()
            self.comm.send_master(grads)
            weights = self.comm.recv_master()
            self.ml.set_weights(weights)
            self.stop = self.comm.recv_master()


    def run(self):
        
        self.create_base_path()
        self.setup()

        if self.comm.is_master():
            self.master_train()
        else:
            self.worker_train()