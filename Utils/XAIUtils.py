import tensorflow as tf
import torch
from torch.utils.data import DataLoader, TensorDataset


class XAIUtils():
    """
    Methods to implement in the child class:
    - run_tf(self)
    - run_torch(self)
    """

    def __init__(self, dataset, ml, model, model_path, batch_size):
        self.dataset = dataset
        self.ml = ml
        self.model_obj = model
        self.model_path = model_path
        self.batch_size = batch_size
        self.channels = None

        self.model = getattr(self, f"load_model_{ml}")()
        self.data = getattr(self, f"load_data_{ml}")()


    def load_model_torch(self):
        model = self.model_obj.get_model(self.ml, self.dataset)
        model.load_state_dict(torch.load(self.model_path))
        model.eval()

        return model
    

    def load_data_torch(self):
        x_test, y_test = self.dataset.load_data("test")
        x_test = torch.tensor(x_test)
        y_test = torch.tensor(y_test)

        data_type = "tabular" if "Tabular" in self.dataset.metadata["type"] else "image"

        if data_type == "tabular":
            return x_test.float(), y_test

        elif data_type == "image":
            if len(x_test.shape) == 4:
                self.channels = x_test.shape[-1]
                x_test = x_test.permute(0, 3, 1, 2)
            else:
                self.channels = 1
                width = x_test.shape[1]
                height = x_test.shape[2]
                x_test = x_test.reshape(-1, 1, width, height)

            y_test = y_test.reshape(-1)
            
            test_dataset = TensorDataset(x_test, y_test)
            test_dataloader = DataLoader(test_dataset, batch_size=self.batch_size, shuffle=False)

            return test_dataloader


    def load_model_tf(self):
        return tf.keras.models.load_model(self.model_path)
    

    def load_data_tf(self):
        return self.dataset.load_data("test")


    def run(self, file):
        getattr(self, f"run_{self.ml}")(file)