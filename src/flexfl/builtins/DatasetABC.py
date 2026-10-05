import json
import os
import random
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np
import wget
from sklearn.model_selection import train_test_split

METADATA_FOLDER = Path(__file__).parent.parent / "datasets/_metadata"
DATA_FOLDER = "data"
SCALING_FILE = "scaling.json"
TARGET_FILE = "target_scaling.json"


class DatasetABC(ABC):

    def __init__(
        self, *, data_name: str = None, data_folder: str = None, **kwargs
    ) -> None:
        self.name = self.__class__.__name__ if data_name is None else data_name
        self.metadata_file = f"{METADATA_FOLDER}/{self.name}.json"
        self.base_path = f"{DATA_FOLDER}/{self.name}"
        self.default_folder = f"{self.base_path}/_data"
        self.output_size = 1
        if data_folder is not None:
            self.data_path = f"{self.base_path}/{data_folder}"
        elif (env_folder := os.getenv("DATA_FOLDER")) is not None:
            self.data_path = f"{self.base_path}/{env_folder}"
        else:
            self.data_path = self.default_folder
        self.metadata = {}
        self.load_metadata()

    @property
    @abstractmethod
    def is_classification(self) -> bool:
        """
        Returns True if the dataset is a classification dataset
        """
        pass

    @property
    @abstractmethod
    def scaler(self) -> Any:
        """
        Returns the scaler object
        """
        pass

    @abstractmethod
    def download(self):
        """
        Downloads the dataset
        """
        pass

    @abstractmethod
    def preprocess(self, val_size, test_size):
        """
        Preprocesses the dataset
        """
        pass

    def load_metadata(self):
        path = Path(self.metadata_file)
        if path.exists():
            with open(path, "r") as file:
                self.metadata = json.load(file)
        else:
            self.metadata = {
                "name": self.name,
                "link": "",
                "type": "classification" if self.is_classification else "regression",
                "output_size": self.output_size,
                "info": "",
            }
            self.save_metadata()

    def save_metadata(self):
        with open(self.metadata_file, "w") as file:
            json.dump(self.metadata, file, indent=4)

    def save_data(self, x, y, split):
        for name, arr in (("x", x), ("y", y)):
            if np.asarray(arr).dtype == object:
                raise ValueError(
                    f"{type(self).__name__}: {name}_{split} has dtype=object; "
                    f"the ML backends cannot convert it to a tensor. "
                    f"Preprocess it to a numeric dtype."
                )
        folder = Path(self.data_path)
        folder.mkdir(parents=True, exist_ok=True)
        np.save(folder / f"x_{split}.npy", x)
        np.save(folder / f"y_{split}.npy", y)

    def load_data(self, split, loader=None):
        x: np.ndarray = np.load(f"{self.data_path}/x_{split}.npy", allow_pickle=True)
        y: np.ndarray = np.load(f"{self.data_path}/y_{split}.npy", allow_pickle=True)
        if loader == "tf":
            import tensorflow as tf

            x = tf.data.Dataset.from_tensor_slices(x)
        elif loader == "torch":
            import torch

            x = torch.tensor(x, dtype=torch.float32)
        return x, y

    def split_data(self, x, y, val_size, test_size):
        total_size = val_size + test_size
        assert total_size < 1, "val_size + test_size must be less than 1"
        if total_size == 0:
            return x, y, None, None, None, None
        x_train, x_remaining, y_train, y_remaining = train_test_split(
            x, y, test_size=total_size, random_state=42, shuffle=True
        )
        if val_size > 0 and test_size > 0:
            x_val, x_test, y_val, y_test = train_test_split(
                x_remaining,
                y_remaining,
                test_size=test_size / total_size,
                random_state=42,
                shuffle=True,
            )
            return x_train, y_train, x_val, y_val, x_test, y_test
        elif val_size > 0:
            return x_train, y_train, x_remaining, y_remaining, None, None
        else:
            return x_train, y_train, None, None, x_remaining, y_remaining

    def split_save(self, x, y, val_size=0.15, test_size=0.15):
        self.metadata["samples"] = x.shape[0]
        self.metadata["input_shape"] = x.shape[1:]
        if self.is_classification:
            self.output_size = len(np.unique(y))
        self.metadata["output_size"] = self.output_size
        x_train, y_train, x_val, y_val, x_test, y_test = self.split_data(
            x, y, val_size, test_size
        )
        scaler = self.scaler()
        x_train = scaler.fit_transform(x_train)
        x_val = scaler.transform(x_val)
        x_test = scaler.transform(x_test)
        if not (hasattr(scaler, "mean_") and hasattr(scaler, "scale_")):
            raise TypeError(
                f"{self.name}: scaler {type(scaler).__name__} exposes no mean_/scale_, "
                f"so {SCALING_FILE} cannot record the fitted statistics."
            )
        target = None if self.is_classification else self.fit_target(y_train)
        (Path(self.data_path) / SCALING_FILE).unlink(missing_ok=True)
        self.save_data(x_train, y_train, "train")
        self.save_data(x_val, y_val, "val")
        self.save_data(x_test, y_test, "test")
        self.metadata["split"] = {
            "train": f"{(1-val_size-test_size)*100:.2f}%: {x_train.shape[0]}",
            "val": f"{val_size*100:.2f}%: {x_val.shape[0]}",
            "test": f"{test_size*100:.2f}%: {x_test.shape[0]}",
        }
        self.save_metadata()
        self.save_scaling(scaler, x_train.shape[0], target)

    def save_scaling(self, scaler, n_samples, target=None):
        # Keep this write last and atomic: the sweep and check_scaled_cache treat the
        # file as proof that the whole cache was rebuilt and scaled.
        stats = {
            "scaler": type(scaler).__name__,
            "fitted_on": "train",
            "n_samples": int(n_samples),
            "mean": scaler.mean_.tolist(),
            "scale": scaler.scale_.tolist(),
            "target": target,
        }
        path = Path(self.data_path) / SCALING_FILE
        tmp = path.with_name(path.name + ".tmp")
        try:
            with open(tmp, "w") as file:
                json.dump(stats, file, indent=4)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    def fit_target(self, y_train):
        y = np.asarray(y_train, dtype=np.float64)
        mean = float(y.mean())
        scale = float(y.std())
        if not (np.isfinite(mean) and np.isfinite(scale)):
            raise ValueError(
                f"{self.name}: the training targets are not finite, so they cannot "
                f"be standardized."
            )
        if scale == 0.0:
            scale = 1.0
        return {
            "fitted_on": "train",
            "n_samples": int(y.shape[0]),
            "mean": mean,
            "scale": scale,
        }

    @staticmethod
    def unscale_target(values, target):
        return np.asarray(values, dtype=np.float64) * target["scale"] + target["mean"]

    @staticmethod
    def valid_target(target):
        if not isinstance(target, dict):
            return False
        mean, scale = target.get("mean"), target.get("scale")
        return (
            isinstance(mean, (int, float))
            and isinstance(scale, (int, float))
            and np.isfinite(mean)
            and np.isfinite(scale)
            and scale > 0
        )

    def target_stats(self):
        if self.is_classification:
            return None
        if Path(self.data_path) != Path(self.default_folder):
            path = Path(self.data_path) / TARGET_FILE
            target = None
            if path.is_file():
                with open(path) as file:
                    target = json.load(file)
            if not self.valid_target(target):
                raise FileNotFoundError(
                    f"{self.name}: {path} is missing or invalid, so regression "
                    f"predictions cannot be de-standardized. Re-run flexfl-division "
                    f"for this dataset."
                )
            return target
        path = Path(self.default_folder) / SCALING_FILE
        target = None
        if path.is_file():
            with open(path) as file:
                target = json.load(file).get("target")
        if not self.valid_target(target):
            raise FileNotFoundError(
                f"{self.name}: {path} has no valid target statistics. Re-run "
                f"flexfl-preprocess for this dataset."
            )
        return target

    def save_target(self, target, standardized):
        with open(Path(self.data_path) / TARGET_FILE, "w") as file:
            json.dump({**target, "standardized": standardized}, file, indent=4)

    def check_scaled_cache(self):
        path = Path(self.default_folder) / SCALING_FILE
        if not path.is_file():
            raise FileNotFoundError(
                f"{self.name}: {self.default_folder} has no {SCALING_FILE}, so its "
                f"splits were not centrally scaled. Re-run flexfl-preprocess for "
                f"this dataset before dividing it."
            )
        if self.is_classification:
            return
        with open(path) as file:
            target = json.load(file).get("target")
        if not self.valid_target(target):
            raise FileNotFoundError(
                f"{self.name}: {path} has no valid target statistics, so its "
                f"regression targets cannot be standardized. Re-run "
                f"flexfl-preprocess for this dataset before dividing it."
            )

    def save_features(self, features):
        self.metadata["features"] = "|".join(features)
        self.save_metadata()

    def data_division(
        self,
        num_workers,
        val_size=0,
        test_size=0,
        distribution="iid",
        distribution_percentage=0.9,
        alpha=0.5,
    ):
        self.check_scaled_cache()
        for folder in Path(self.base_path).glob("node_*"):
            for file in folder.glob("*"):
                file.unlink()
            folder.rmdir()
        self.data_path = self.default_folder
        target = self.target_stats()
        self.division_master(target)

        if distribution == "iid":
            x, y = self.division_iid(num_workers)
        elif distribution == "dirichlet":
            x, y = self.division_non_iid_dirichlet(num_workers, alpha)
        else:
            x, y = self.division_non_iid(num_workers, distribution_percentage)
        for i in range(num_workers):
            if len(x[i]) == 0:
                raise ValueError(
                    f"{self.name}: worker {i+1}/{num_workers} received 0 training "
                    f"samples under distribution='{distribution}' (dataset too small "
                    f"for this worker count, or an extreme non-iid/dirichlet skew) -- "
                    f"reduce num_workers or adjust distribution_percentage/alpha for "
                    f"this dataset."
                )
            self.division_worker(x[i], y[i], i + 1, val_size, test_size, target)

    def division_master(self, target=None):
        self.data_path = self.default_folder
        x, y = self.load_data("val")
        self.data_path = f"{self.base_path}/node_0"
        self.save_data(x, y, "val")
        if target is not None:
            self.save_target(target, standardized=False)

    def division_iid(self, num_workers):
        self.data_path = self.default_folder
        x, y = self.load_data("train")
        x = np.array_split(x, num_workers)
        y = np.array_split(y, num_workers)
        return x, y

    def division_non_iid(self, num_workers, distribution_percentage, seed=42):
        self.data_path = self.default_folder
        x, y = self.load_data("train")
        if self.metadata["type"] == "classification":
            classes = list(np.unique(y))
        else:
            bins = np.histogram_bin_edges(y, bins="auto")
            # remove the last index (end point)
            bins[-1] += 1
            classes = [(bins[x], bins[x + 1]) for x in range(len(bins) - 1)]

            remove_classes = []
            for classe in classes:
                indx = np.where((y >= classe[0]) & (y < classe[1]))[0]
                if len(indx) == 0:
                    remove_classes.append(1)
                else:
                    remove_classes.append(0)

            updated_classes = []
            pending_start = None
            for idx, class_to_remove in enumerate(remove_classes):
                if class_to_remove:
                    if updated_classes:
                        updated_classes[-1] = (updated_classes[-1][0], classes[idx][1])
                    else:
                        pending_start = classes[idx][0]
                else:
                    start = (
                        pending_start if pending_start is not None else classes[idx][0]
                    )
                    updated_classes.append((start, classes[idx][1]))
                    pending_start = None

            classes = updated_classes

        rng = random.Random(seed)
        workers = list(range(num_workers))
        workers_x = [0] * num_workers
        workers_y = [0] * num_workers

        if num_workers > len(classes):
            counts = [1] * len(classes)
            for i in range(num_workers - len(classes)):
                idx = i % len(counts)
                counts[idx] += 1

            dist = rng.sample(classes, k=num_workers, counts=counts)
        else:
            counts = [1] * num_workers
            for i in range(len(classes) - num_workers):
                idx = i % num_workers
                counts[idx] += 1

            dist = rng.sample(workers, k=len(classes), counts=counts)
            temp_dist = [0] * num_workers

            for idx, c in enumerate(classes):
                if temp_dist[dist[idx]] == 0:
                    temp_dist[dist[idx]] = {c}
                else:
                    temp_dist[dist[idx]].add(c)
            dist = temp_dist

        for idx, c in enumerate(classes):
            indexes = (
                np.where(y == c)[0]
                if self.metadata["type"] == "classification"
                else np.where((y >= c[0]) & (y < c[1]))[0]
            )

            in_class = indexes[: int(len(indexes) * distribution_percentage)]
            out_class = indexes[int(len(indexes) * distribution_percentage) :]
            in_count = 0
            out_count = 0

            if num_workers > len(classes):
                in_subset_size = len(in_class) // counts[idx]
                out_subset_size = len(out_class) // (num_workers - counts[idx])

            else:
                out_subset_size = len(out_class) // (num_workers - 1)

            for worker in workers:
                if num_workers > len(classes):
                    if dist[worker] == c:
                        worker_x_values = (
                            x[in_class]
                            if counts[idx] == 1
                            else x[
                                in_class[
                                    in_count
                                    * in_subset_size : in_count
                                    * in_subset_size
                                    + in_subset_size
                                ]
                            ]
                        )
                        worker_y_values = (
                            y[in_class]
                            if counts[idx] == 1
                            else y[
                                in_class[
                                    in_count
                                    * in_subset_size : in_count
                                    * in_subset_size
                                    + in_subset_size
                                ]
                            ]
                        )

                        in_count += 1
                    else:
                        worker_x_values = (
                            x[out_class]
                            if num_workers - counts[idx] == 1
                            else x[
                                out_class[
                                    out_count
                                    * out_subset_size : out_count
                                    * out_subset_size
                                    + out_subset_size
                                ]
                            ]
                        )

                        worker_y_values = (
                            y[out_class]
                            if num_workers - counts[idx] == 1
                            else y[
                                out_class[
                                    out_count
                                    * out_subset_size : out_count
                                    * out_subset_size
                                    + out_subset_size
                                ]
                            ]
                        )
                        out_count += 1
                else:
                    if c in dist[worker]:
                        worker_x_values = x[in_class]
                        worker_y_values = y[in_class]
                    else:
                        worker_x_values = x[
                            out_class[
                                out_count
                                * out_subset_size : out_count
                                * out_subset_size
                                + out_subset_size
                            ]
                        ]
                        worker_y_values = y[
                            out_class[
                                out_count
                                * out_subset_size : out_count
                                * out_subset_size
                                + out_subset_size
                            ]
                        ]

                        out_count += 1

                if type(workers_x[worker]) is int:
                    workers_x[worker] = [worker_x_values]
                    workers_y[worker] = [worker_y_values]
                else:
                    workers_x[worker].append(worker_x_values)
                    workers_y[worker].append(worker_y_values)

        for worker in workers:
            workers_x[worker] = np.concatenate(workers_x[worker], axis=0)
            workers_y[worker] = np.concatenate(workers_y[worker], axis=0)

        return workers_x, workers_y

    def division_non_iid_dirichlet(self, num_workers, alpha=0.5, seed=42):
        self.data_path = self.default_folder
        x, y = self.load_data("train")
        rng = np.random.default_rng(seed)

        if self.metadata["type"] == "classification":
            classes = list(np.unique(y))

            def get_indexes(c):
                return np.where(y == c)[0]

        else:
            bins = np.histogram_bin_edges(y, bins="auto")
            bins[-1] += 1
            classes = [(bins[i], bins[i + 1]) for i in range(len(bins) - 1)]

            remove_classes = [
                1 if len(np.where((y >= c[0]) & (y < c[1]))[0]) == 0 else 0
                for c in classes
            ]
            updated_classes = []
            pending_start = None
            for idx, class_to_remove in enumerate(remove_classes):
                if class_to_remove:
                    if updated_classes:
                        updated_classes[-1] = (updated_classes[-1][0], classes[idx][1])
                    else:
                        pending_start = classes[idx][0]
                else:
                    start = (
                        pending_start if pending_start is not None else classes[idx][0]
                    )
                    updated_classes.append((start, classes[idx][1]))
                    pending_start = None
            classes = updated_classes

            def get_indexes(c):
                return np.where((y >= c[0]) & (y < c[1]))[0]

        workers_x = [[] for _ in range(num_workers)]
        workers_y = [[] for _ in range(num_workers)]

        for c in classes:
            indexes = get_indexes(c)
            if len(indexes) == 0:
                continue
            rng.shuffle(indexes)
            proportions = rng.dirichlet([alpha] * num_workers)
            splits = (np.cumsum(proportions[:-1]) * len(indexes)).astype(int)
            for worker, worker_indexes in enumerate(np.split(indexes, splits)):
                if len(worker_indexes) > 0:
                    workers_x[worker].append(x[worker_indexes])
                    workers_y[worker].append(y[worker_indexes])

        for worker in range(num_workers):
            if workers_x[worker]:
                workers_x[worker] = np.concatenate(workers_x[worker], axis=0)
                workers_y[worker] = np.concatenate(workers_y[worker], axis=0)
            else:
                workers_x[worker] = np.empty((0, *x.shape[1:]), dtype=x.dtype)
                workers_y[worker] = np.empty((0, *y.shape[1:]), dtype=y.dtype)

        return workers_x, workers_y

    def division_worker(self, x, y, worker_id, val_size, test_size, target=None):
        if target is not None:
            y = (np.asarray(y, dtype=np.float64) - target["mean"]) / target["scale"]
        x_train, y_train, x_val, y_val, x_test, y_test = self.split_data(
            x, y, val_size, test_size
        )
        self.data_path = f"{self.base_path}/node_{worker_id}"
        self.save_data(x_train, y_train, "train")
        if val_size > 0:
            self.save_data(x_val, y_val, "val")
        if test_size > 0:
            self.save_data(x_test, y_test, "test")
        if target is not None:
            self.save_target(target, standardized=True)

    def download_file(self, url):
        destination = Path(f"{self.default_folder}/temp.zip")
        destination.parent.mkdir(parents=True, exist_ok=True)
        wget.download(url, str(destination))
        print()
        with zipfile.ZipFile(destination, "r") as zip_ref:
            zip_ref.extractall(destination.parent)
        destination.unlink()
