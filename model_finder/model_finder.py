import optuna
import tensorflow as tf
import numpy as np
import json
from pathlib import Path
from flexfl.datasets.Benchmark import Benchmark

import os

BATCHSIZE = 2560

def create_model(trial, n_classes):
    # We optimize the numbers of layers, their units and weight decay parameter.
    n_layers = trial.suggest_int("n_layers", 1, 12)
    weight_decay = trial.suggest_float("weight_decay", 1e-10, 1e-3, log=True)
    model = tf.keras.Sequential()
    for i in range(n_layers):
        num_hidden_options = [8, 16, 32, 64, 128, 256] 
        num_hidden = trial.suggest_categorical(f"n_units_l{i}", num_hidden_options)
        model.add(
            tf.keras.layers.Dense(
                num_hidden,
                activation="relu",
                kernel_regularizer=tf.keras.regularizers.l2(weight_decay),
            )
        )
    activation = "linear" if n_classes == 1 else "softmax"
    model.add(
        tf.keras.layers.Dense(n_classes, kernel_regularizer=tf.keras.regularizers.l2(weight_decay), activation=activation)
    )
    return model


def create_optimizer(trial):
    # We optimize the choice of optimizers as well as their parameters.
    kwargs = {}
    optimizer_options = ["RMSprop", "Adam", "Adadelta", "Nadam"]
    optimizer_selected = trial.suggest_categorical("optimizer", optimizer_options)

    kwargs["learning_rate"] = trial.suggest_float(
            f"{optimizer_selected}_learning_rate", 1e-5, 1e-1, log=True
        )
    kwargs["weight_decay"] = trial.suggest_float(f"{optimizer_selected}_weight_decay", 0.85, 0.99)
    
    if optimizer_selected == "RMSprop":
        kwargs["momentum"] = trial.suggest_float("rmsprop_momentum", 1e-5, 1e-1, log=True)

    optimizer = getattr(tf.optimizers, optimizer_selected)(**kwargs)
    return optimizer


def learn(model, optimizer, loss_fn, eval_fn, dataset, mode="eval"):
    for _, (samples, labels) in enumerate(dataset):
        with tf.GradientTape() as tape:
            logits = model(samples, training=(mode == "train"))

            loss_value = loss_fn(labels, logits)
            if mode == "eval":
                eval_fn(
                    labels, logits 
                )
            else:
                grads = tape.gradient(loss_value, model.variables)
                optimizer.apply_gradients(zip(grads, model.variables))


def get_dataset(name):
    
    ds = Benchmark(data_name=name)
    try:
        x_train, y_train = ds.load_data("train")
        x_val, y_val = ds.load_data("val")
    except:
        ds.preprocess(0.15, 0.15)
        x_train, y_train = ds.load_data("train")
        x_val, y_val = ds.load_data("val")

    if "clf" in name:
        y_train = tf.keras.utils.to_categorical(y_train, num_classes=ds.metadata["output_size"])
        y_val = tf.keras.utils.to_categorical(y_val, num_classes=ds.metadata["output_size"])

    train_ds = tf.data.Dataset.from_tensor_slices((x_train, y_train))
    train_ds = train_ds.shuffle(x_train.shape[0]).batch(BATCHSIZE)

    val_ds = tf.data.Dataset.from_tensor_slices((x_val, y_val))
    val_ds = val_ds.shuffle(x_val.shape[0]).batch(BATCHSIZE)

    return train_ds, val_ds, ds.metadata["output_size"]


# FYI: Objective functions can take additional arguments
# (https://optuna.readthedocs.io/en/stable/faq.html#objective-func-additional-args).
def objective(trial, dataset_name, epochs):

    train_ds, valid_ds, n_classes = get_dataset(dataset_name)

    # Build model and optimizer.
    model = create_model(trial, n_classes)
    optimizer = create_optimizer(trial)
    loss_fn = tf.keras.losses.MeanSquaredError() if n_classes == 1 else tf.keras.losses.CategoricalCrossentropy()
    eval_fn = tf.keras.metrics.MeanAbsolutePercentageError() if n_classes == 1 else tf.keras.metrics.F1Score(average = "weighted")

    # Training and validating cycle.
    with tf.device("/gpu:0"):
        for _ in range(epochs):
            learn(model, optimizer, loss_fn, eval_fn, train_ds, "train")

        learn(model, optimizer, loss_fn, eval_fn, valid_ds, "eval")

    # Return last validation accuracy.
    return eval_fn.result()


if __name__ == "__main__":
    datasets_info = json.load(open("datasets.json"))
    epochs = 200
    trials = 100
    result_folder = "results/hyperparameter_optimization/"
    result_folder = Path(result_folder)
    result_folder.mkdir(parents=True, exist_ok=True)


    for dataset in datasets_info["splits"]:    
        print(dataset['config'])
        if dataset["config"] not in ["clf_cat_electricity", "clf_num_MagicTelescope", "clf_num_MiniBooNE", "clf_num_electricity", "clf_num_house_16H", "clf_num_pol"]:
            result_file = result_folder / f"{dataset['config']}.json"
            
            study = optuna.create_study(direction="maximize") if "clf" in dataset["config"] else optuna.create_study(direction="minimize")
            study.optimize(lambda trial: objective(trial, dataset["config"], epochs), n_trials=trials)

            print("Number of finished trials: ", len(study.trials))

            print("Best trial:")
            trial = study.best_trial

            print("  Value: ", trial.value)

            print("  Params: ")
            for key, value in trial.params.items():
                print("    {}: {}".format(key, value))
            json.dump(trial.params, open(result_file, "w"), indent=2)

            