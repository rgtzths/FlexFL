import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from itertools import cycle
import os

from flexfl.builtins.MLFrameworkABC import MLFrameworkABC


OPTIMIZERS = {
    'adam': optim.Adam,
    'sgd': optim.SGD,
    'rmsprop': optim.RMSprop,
}

LOSSES = {
    'mse': nn.MSELoss,
    'mae': nn.L1Loss,
    'mape': lambda: lambda y_pred, y_true: torch.mean(torch.abs((y_true - y_pred) / y_true)),
    'scc': nn.CrossEntropyLoss,
}


class PyTorch(MLFrameworkABC):
    

    @property
    def prefix(self) -> str:
        return "torch"
    

    def set_seed(self, seed: int):
        torch.manual_seed(seed)
    

    def get_device(self):
        if os.environ.get("CUDA_VISIBLE_DEVICES") == -1:
            return torch.device("cpu")
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    

    def setup(self):
        self.device = self.get_device()
        self.optimizer = OPTIMIZERS[self.optimizer_name](self.model.parameters(), lr=self.learning_rate)
        self.loss = LOSSES[self.loss_name]()
        self.model.to(self.device)


    def load_data(self, split: str):
        x_tensor, y = self.dataset.load_data(split, loader="torch")
        x_tensor = x_tensor.to(self.device)
        self.n_samples = y.shape[0]
        y_tensor = torch.tensor(y, dtype=torch.long).to(self.device)
        dataset = torch.utils.data.TensorDataset(x_tensor, y_tensor)
        data_loader = torch.utils.data.DataLoader(dataset, batch_size=self.batch_size, shuffle=True)
        setattr(self, f"x_{split}", x_tensor)
        setattr(self, f"y_{split}", y)
        setattr(self, f"{split}_data", data_loader)
        setattr(self, f"{split}_iterator", cycle(data_loader))


    def get_weights(self):
        return np.concatenate([param.detach().cpu().numpy().flatten() for param in self.model.parameters()])
    

    def set_weights(self, weights: np.ndarray):
        start = 0
        new_weights = []
        for param in self.model.parameters():
            size = np.prod(param.shape)
            new_weights.append(torch.tensor(weights[start:start + size].reshape(param.shape), dtype=torch.float32).to(self.device))
            start += size
        with torch.no_grad():
            for param, new_weight in zip(self.model.parameters(), new_weights):
                param.copy_(new_weight)


    def calculate_gradients(self):
        raise NotImplementedError
    

    def apply_gradients(self, gradients: np.ndarray):
        raise NotImplementedError
    

    def train(self, epochs: int, verbose=False):
        self.model.train()
        for epoch in range(epochs):
            for x_batch, y_batch in self.train_data:
                x_batch, y_batch = x_batch.to(self.device), y_batch.to(self.device)
                self.optimizer.zero_grad()
                y_pred = self.model(x_batch)
                loss = self.loss(y_pred, y_batch)
                loss.backward()
                self.optimizer.step()
            if verbose:
                print(f"Epoch {epoch+1}/{epochs}, Loss: {loss.item()}")
    

    def predict(self, data):
        self.model.eval()
        data_tensor = data.clone().detach().to(self.device)
        with torch.no_grad():
            return self.model(data_tensor).cpu().numpy()

    

    def calculate_loss(self, y_true: np.ndarray, y_pred: np.ndarray) -> float:
        y_true_tensor = torch.tensor(y_true, dtype=torch.long).to(self.device)
        y_pred_tensor = torch.tensor(y_pred, dtype=torch.float32).to(self.device)
        return self.loss(y_pred_tensor, y_true_tensor).item()
    

    def save_model(self, path):
        torch.save(self.model.state_dict(), f"{path}.pt")
    

    def load_model(self, path):
        self.model.load_state_dict(torch.load(f"{path}.pt", map_location=self.device))
        self.model.to(self.device)
