import numpy as np
from pathlib import Path
import json
from sklearn.model_selection import train_test_split
import wget
import zipfile
import pprint


class DatasetUtils:
    """
    Methods to implement in the child class:
    - download(self)
    - preprocess(self, val_size, test_size)
    - {ml}_model(self)
    """

    def __init__(self):
        self.name = self.__class__.__name__
        self.metadata = {}
        self.load_metadata()
    

    def load_metadata(self):
        path = Path(f'Datasets/Metadata/{self.name}.json')
        if path.exists():
            with open(path, 'r') as file:
                self.metadata = json.load(file)
        else:
            self.metadata = {"name": self.name, "link": "", "type": "", "info": ""}
            self.save_metadata()


    def save_metadata(self):
        path = Path(f'Datasets/Metadata/{self.name}.json')
        with open(path, 'w') as file:
            json.dump(self.metadata, file, indent=4)
        

    def save_data(self, x, y, split):
        folder = Path(f'Data/{self.name}')
        folder.mkdir(parents=True, exist_ok=True)
        np.save(folder/f'x_{split}.npy', x)
        np.save(folder/f'y_{split}.npy', y)


    def load_data(self, split):
        folder = Path(f'Data/{self.name}')
        x = np.load(folder/f'x_{split}.npy')
        y = np.load(folder/f'y_{split}.npy')
        self.n_samples = x.shape[0]
        return x, y
    

    def split_save(self, x, y, val_size, test_size, scaler=None):
        self.metadata['samples'] = x.shape[0]
        self.metadata['input_shape'] = x.shape[1:]
        x_train, x, y_train, y = train_test_split(x, y, test_size=val_size+test_size, random_state=42, shuffle=True)
        x_val, x_test, y_val, y_test = train_test_split(x, y, test_size=test_size/(val_size+test_size), random_state=42, shuffle=True)
        if scaler is not None:
            x_train = scaler.fit_transform(x_train)
            x_val = scaler.transform(x_val)
            x_test = scaler.transform(x_test)
        self.save_data(x_train, y_train, 'train')
        self.save_data(x_val, y_val, 'val')
        self.save_data(x_test, y_test, 'test')
        self.metadata['split'] = {
            'train': f"{(1-val_size-test_size)*100:.2f}%: {x_train.shape[0]}",
            'val': f"{val_size*100:.2f}%: {x_val.shape[0]}",
            'test': f"{test_size*100:.2f}%: {x_test.shape[0]}"
        }
        self.save_metadata()


    def save_features(self, features):
        self.metadata['features'] = '|'.join(features)
        self.save_metadata()
    

    def save_worker_data(self, x, y, worker_id, num_workers):
        folder = Path(f'Data/{self.name}/{num_workers}_workers')
        folder.mkdir(parents=True, exist_ok=True)
        np.save(folder/f'x_{worker_id}.npy', x)
        np.save(folder/f'y_{worker_id}.npy', y)


    def load_worker_data(self, worker_id, num_workers):
        folder = Path(f'Data/{self.name}/{num_workers}_workers')
        x = np.load(folder/f'x_{worker_id}.npy')
        y = np.load(folder/f'y_{worker_id}.npy')
        self.n_samples = x.shape[0]
        return x, y
    

    def data_division(self, num_workers):
        x, y = self.load_data('train')
        x = np.array_split(x, num_workers)
        y = np.array_split(y, num_workers)
        for i in range(num_workers):
            self.save_worker_data(x[i], y[i], i, num_workers)


    def download_file(self, url):
        destination = Path(f"Data/{self.name}/temp.zip")
        destination.parent.mkdir(parents=True, exist_ok=True)
        wget.download(url, str(destination))
        print()
        with zipfile.ZipFile(destination, 'r') as zip_ref:
            zip_ref.extractall(destination.parent)
        destination.unlink()
    

    def __str__(self):
        return pprint.pformat(self.metadata)