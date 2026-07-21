"""Simple training-time benchmark for a few Keras models."""

import argparse
import json
import os
import time

import numpy as np
import tqdm

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("KERAS_BACKEND", "tensorflow")

try:
    import keras
    from keras import layers
except Exception as exc:  # pragma: no cover - import-time guard
    raise SystemExit(
        "Keras backend is not available. Install the ml extra (pip install '.[ml]') or set KERAS_BACKEND."
    ) from exc


def build_small_mlp(input_dim: int, classes: int) -> keras.Model:
    return keras.Sequential(
        [
            layers.Input(shape=(input_dim,)),
            layers.Dense(128, activation="relu"),
            layers.Dense(64, activation="relu"),
            layers.Dense(classes, activation="softmax"),
        ],
        name="small_mlp",
    )


def build_medium_mlp(input_dim: int, classes: int) -> keras.Model:
    return keras.Sequential(
        [
            layers.Input(shape=(input_dim,)),
            layers.Dense(512, activation="relu"),
            layers.Dense(256, activation="relu"),
            layers.Dense(128, activation="relu"),
            layers.Dense(classes, activation="softmax"),
        ],
        name="medium_mlp",
    )


def build_large_mlp(input_dim: int, classes: int) -> keras.Model:
    return keras.Sequential(
        [
            layers.Input(shape=(input_dim,)),
            layers.Dense(1024, activation="relu"),
            layers.Dense(512, activation="relu"),
            layers.Dense(256, activation="relu"),
            layers.Dense(128, activation="relu"),
            layers.Dense(classes, activation="softmax"),
        ],
        name="large_mlp",
    )


def build_conv1d(input_shape: tuple[int, int], classes: int) -> keras.Model:
    return keras.Sequential(
        [
            layers.Input(shape=input_shape),
            layers.Conv1D(64, kernel_size=3, activation="relu"),
            layers.MaxPooling1D(pool_size=2),
            layers.Conv1D(128, kernel_size=3, activation="relu"),
            layers.GlobalMaxPooling1D(),
            layers.Dense(128, activation="relu"),
            layers.Dense(classes, activation="softmax"),
        ],
        name="conv1d",
    )


def build_lstm(input_shape: tuple[int, int], classes: int) -> keras.Model:
    return keras.Sequential(
        [
            layers.Input(shape=input_shape),
            layers.LSTM(64),
            layers.Dense(64, activation="relu"),
            layers.Dense(classes, activation="softmax"),
        ],
        name="lstm",
    )


def build_conv2d(input_shape: tuple[int, int, int], classes: int) -> keras.Model:
    return keras.Sequential(
        [
            layers.Input(shape=input_shape),
            layers.Conv2D(32, kernel_size=(3, 3), activation="relu"),
            layers.MaxPooling2D(pool_size=(2, 2)),
            layers.Conv2D(64, kernel_size=(3, 3), activation="relu"),
            layers.MaxPooling2D(pool_size=(2, 2)),
            layers.Flatten(),
            layers.Dense(128, activation="relu"),
            layers.Dense(classes, activation="softmax"),
        ],
        name="conv2d",
    )


MODEL_SPECS = {
    "small": {"builder": build_small_mlp, "input": "flat"},
    "medium": {"builder": build_medium_mlp, "input": "flat"},
    "large": {"builder": build_large_mlp, "input": "flat"},
    "conv": {"builder": build_conv1d, "input": "sequence"},
    "lstm": {"builder": build_lstm, "input": "sequence"},
    "conv2d": {"builder": build_conv2d, "input": "image"},
}


def make_flat_dataset(
    samples: int,
    features: int,
    classes: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(samples, features)).astype("float32")
    y = rng.integers(0, classes, size=(samples,), dtype=np.int64)
    return x, y


def make_sequence_dataset(
    samples: int,
    seq_len: int,
    seq_features: int,
    classes: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(samples, seq_len, seq_features)).astype("float32")
    y = rng.integers(0, classes, size=(samples,), dtype=np.int64)
    return x, y


def make_image_dataset(
    samples: int,
    height: int,
    width: int,
    channels: int,
    classes: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(samples, height, width, channels)).astype("float32")
    y = rng.integers(0, classes, size=(samples,), dtype=np.int64)
    return x, y


def train_and_time(
    model: keras.Model,
    x: np.ndarray,
    y: np.ndarray,
    epochs: int,
    batch_size: int,
    warmup_epochs: int,
) -> float:
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=1e-3),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )

    if warmup_epochs > 0:
        model.fit(x, y, epochs=warmup_epochs, batch_size=batch_size, verbose=0)

    start = time.perf_counter()
    model.fit(x, y, epochs=epochs, batch_size=batch_size, verbose=0)
    return time.perf_counter() - start

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Train a few Keras models and time them.")
    parser.add_argument(
        "--models",
        default="small,medium,large,conv,lstm,conv2d",
        help="Comma-separated list: small,medium,large,conv,lstm,conv2d",
    )
    parser.add_argument("--samples", type=int, default=50000)
    parser.add_argument("--features", type=int, default=100)
    parser.add_argument("--seq-len", type=int, default=50)
    parser.add_argument("--seq-features", type=int, default=8)
    parser.add_argument("--img-height", type=int, default=28)
    parser.add_argument("--img-width", type=int, default=28)
    parser.add_argument("--img-channels", type=int, default=1)
    parser.add_argument("--classes", type=int, default=10)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--warmup-epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output",
        default="results/machine_benchmark.json",
        help="Where to save the JSON results",
    )
    args = parser.parse_args()

    model_names = [name.strip() for name in args.models.split(",") if name.strip()]
    for name in model_names:
        if name not in MODEL_SPECS:
            raise SystemExit(f"Unknown model: {name}")
    
    keras.utils.set_random_seed(args.seed)
    
    need_flat = any(MODEL_SPECS[name]["input"] == "flat" for name in model_names)
    need_seq = any(MODEL_SPECS[name]["input"] == "sequence" for name in model_names)
    need_img = any(MODEL_SPECS[name]["input"] == "image" for name in model_names)
    
    results: dict[str, list[float]] = {}
    flat_data: tuple[np.ndarray, np.ndarray] | None = None
    seq_data: tuple[np.ndarray, np.ndarray] | None = None
    img_data: tuple[np.ndarray, np.ndarray] | None = None
    
    for name in tqdm.tqdm(model_names, desc="Evaluating Models"):
        spec = MODEL_SPECS[name]
        if spec["input"] == "flat":
            if flat_data is None:
                flat_data = make_flat_dataset(
                    args.samples,
                    args.features,
                    args.classes,
                    args.seed,
                )
            x, y = flat_data
            builder_args = (args.features, args.classes)
        elif spec["input"] == "sequence":
            if seq_data is None:
                seq_data = make_sequence_dataset(
                    args.samples,
                    args.seq_len,
                    args.seq_features,
                    args.classes,
                    args.seed,
                )
            x, y = seq_data
            builder_args = ((args.seq_len, args.seq_features), args.classes)
        else:
            if img_data is None:
                img_data = make_image_dataset(
                    args.samples,
                    args.img_height,
                    args.img_width,
                    args.img_channels,
                    args.classes,
                    args.seed,
                )
            x, y = img_data
            builder_args = (
                (args.img_height, args.img_width, args.img_channels),
                args.classes,
            )
    
        builder = spec["builder"]
        times: list[float] = []
        for run in tqdm.tqdm(range(args.repeats), desc="Running Trials", leave=False):
            keras.backend.clear_session()
            model = builder(*builder_args)
            duration = train_and_time(
                model,
                x,
                y,
                epochs=args.epochs,
                batch_size=args.batch_size,
                warmup_epochs=args.warmup_epochs,
            )
            times.append(duration)
        results[name] = times
    
    print("-\nSummary:")
    output_models: dict[str, dict[str, float | list[float]]] = {}
    for name in model_names:
        avg = sum(results[name]) / len(results[name])
        avg_eps = args.epochs / avg
        output_models[name] = {
            "runs_s": results[name],
            "avg_total_s": avg,
            "epochs_per_second": [args.epochs / run_s for run_s in results[name]],
            "avg_epochs_per_second": avg_eps,
        }
        print(f"{name:<7} avg: {avg:.2f}s total, {avg_eps:.3f} epochs/s")
    
    data_info: dict[str, dict[str, int]] = {}
    if need_flat:
        data_info["flat"] = {
            "samples": args.samples,
            "features": args.features,
        }
    if need_seq:
        data_info["sequence"] = {
            "samples": args.samples,
            "seq_len": args.seq_len,
            "seq_features": args.seq_features,
        }
    if need_img:
        data_info["image"] = {
            "samples": args.samples,
            "height": args.img_height,
            "width": args.img_width,
            "channels": args.img_channels,
        }
    
    output_payload = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "backend": keras.backend.backend(),
        "config": {
            "models": model_names,
            "classes": args.classes,
            "epochs": args.epochs,
            "warmup_epochs": args.warmup_epochs,
            "batch_size": args.batch_size,
            "repeats": args.repeats,
            "seed": args.seed,
        },
        "data": data_info,
        "results": output_models,
    }
    
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(output_payload, handle, indent=2)
    print(f"Saved results to: {args.output}")
