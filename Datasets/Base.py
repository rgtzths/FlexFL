import numpy as np
from pathlib import Path
import json
import requests

class Base:

    def __init__(self):
        self.metadata = {}
        self.load_metadata()


    @property
    def name(self):
        return self.__class__.__name__


    def process_data(self):
        """
        Implement this method to process the raw data and save the processed data
        """
        raise NotImplementedError(f"process_data not implemented in {self.name}")
    

    def call_fn(self, fn, *args, **kwargs):
        if hasattr(self, fn):
            return getattr(self, fn)(*args, **kwargs)
        else:
            raise NotImplementedError(f"{fn} not implemented in {self.name}")
    

    def load_metadata(self):
        path = Path(f'Datasets/Metadata/{self.name}.json')
        if path.exists():
            with open(path, 'r') as file:
                self.metadata = json.load(file)


    def save_metadata(self):
        path = Path(f'Datasets/Metadata/{self.name}.json')
        with open(path, 'w') as file:
            json.dump(self.metadata, file, indent=4)


    def download(self):
        if 'download' not in self.metadata:
            print(f"Download link not available for {self.name}, add it to the metadata as 'download'")
            return
        url = self.metadata['download']
        local_filename = url.split('/')[-1]
        self.edit_metadata('raw', local_filename)
        folder = Path(f'Data/{self.name}')
        folder.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(folder/local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        

    def save_data(self, x, y, split):
        folder = Path(f'Data/{self.name}')
        folder.mkdir(parents=True, exist_ok=True)
        np.save(folder/f'x_{split}.npy', x)
        np.save(folder/f'y_{split}.npy', y)


    def load_data(self, split):
        folder = Path(f'Data/{self.name}')
        x = np.load(folder/f'x_{split}.npy')
        y = np.load(folder/f'y_{split}.npy')
        return x, y
    

    def save_worker_data(self, x, y, worker_id, num_workers):
        folder = Path(f'Data/{self.name}/{num_workers}_workers')
        folder.mkdir(parents=True, exist_ok=True)
        np.save(folder/f'x_{worker_id}.npy', x)
        np.save(folder/f'y_{worker_id}.npy', y)


    def load_worker_data(self, worker_id, num_workers):
        folder = Path(f'Data/{self.name}/{num_workers}_workers')
        x = np.load(folder/f'x_{worker_id}.npy')
        y = np.load(folder/f'y_{worker_id}.npy')
        return x, y
    

    def data_division(self, num_workers):
        x, y = self.load_data('train')
        x = np.array_split(x, num_workers)
        y = np.array_split(y, num_workers)
        for i in range(num_workers):
            self.save_worker_data(x[i], y[i], i, num_workers)


    def tf_load_data(self, split):
        return self.load_data(split)
    

    def torch_load_data(self, split):
        return self.load_data(split)
    

    def tf_worker_data(self, worker_id, num_workers):
        return self.load_worker_data(worker_id, num_workers)
    

    def torch_worker_data(self, worker_id, num_workers):
        return self.load_worker_data(worker_id, num_workers)