import json
import numpy as np
import torch
from alibi.explainers import PermutationImportance

from Utils.XAIUtils import XAIUtils


class PI(XAIUtils):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


    def save_importances(self, explanations, filename):
        f_names = explanations.data['feature_names']
        f_importance = explanations.data['feature_importance'][0]
        importances = {f_names[i]: f_importance[i]['mean'] for i in range(len(f_names))}

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

        explainer = PermutationImportance(
            predictor=self.predict_fn_torch, score_fns='accuracy', feature_names=features
        )
        explanations = explainer.explain(X=x_test.numpy(), y=y_test.numpy(), kind='difference')
        self.save_importances(explanations, f"{file}.json")


    # Tensorflow

    def predict_fn_tf(self, X):
        return np.argmax(self.model(X), axis=1)


    def run_tf(self, file):
        x_test, y_test = self.data
        features = self.dataset.metadata["features"].split("|")

        explainer = PermutationImportance(
            predictor=self.predict_fn_tf, score_fns='accuracy', feature_names=features
        )
        explanations = explainer.explain(X=x_test, y=y_test, kind='difference')
        self.save_importances(explanations, f"{file}.json")