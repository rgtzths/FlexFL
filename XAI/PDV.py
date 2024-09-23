import json
import numpy as np
import torch
from alibi.explainers import PartialDependenceVariance

from Utils.XAIUtils import XAIUtils


class PDV(XAIUtils):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


    def save_importances(self, explanations, filename):
        importances = dict(
            zip(explanations.feature_names, explanations.feature_importance[0])
        )

        with open(filename, "w") as f:
            json.dump(importances, f, indent=4)


    # Pytorch

    def predict_fn_torch(self, X):
        inputs = torch.tensor(X)
        preds = torch.argmax(self.model(inputs), dim=1)
        preds = preds.detach().numpy()

        return preds


    def run_torch(self, file):
        x_test, y_test = self.data
        features = self.dataset.metadata["features"].split("|")

        explainer = PartialDependenceVariance(
            predictor=self.predict_fn_torch, feature_names=features
        )
        explanations = explainer.explain(X=x_test.numpy(), method="importance")
        self.save_importances(explanations, f"{file}.json")


    # Tensorflow

    def predict_fn_tf(self, X):
        return np.argmax(self.model(X), axis=1)


    def run_tf(self, file):
        x_test, y_test = self.data
        features = self.dataset.metadata["features"].split("|")

        explainer = PartialDependenceVariance(
            predictor=self.predict_fn_tf, feature_names=features
        )
        explanations = explainer.explain(X=x_test, method="importance")
        self.save_importances(explanations, f"{file}.json")