import pickle
import torch
from alibi.explainers import ALE as Ale

from Utils.XAIUtils import XAIUtils


class ALE(XAIUtils):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


    def save_explanations(self, explanations, filename):
        f_names = explanations.data['feature_names']

        results = {}
        for i, feature in enumerate(f_names):
            results[feature] = {
                'feature_values': explanations.data["feature_values"][i],
                'ale_values': explanations.data["ale_values"][i]
            }

        with open(filename, "wb") as f:
            pickle.dump(results, f)


    # Pytorch

    def predict_fn_torch(self, X):
        X = torch.tensor(X)
        preds = self.model(X)
        
        return preds.detach().numpy()


    def run_torch(self, file):
        x_test, y_test = self.data
        features = self.dataset.metadata["features"].split("|")

        explainer = Ale(self.predict_fn_torch, feature_names=features)
        explanations = explainer.explain(x_test.numpy())
        self.save_explanations(explanations, f"{file}.pkl")


    # Tensorflow

    def run_tf(self, file):
        x_test, y_test = self.data
        features = self.dataset.metadata["features"].split("|")

        explainer = Ale(self.model.predict, feature_names=features)
        explanations = explainer.explain(x_test)
        self.save_explanations(explanations, f"{file}.pkl")