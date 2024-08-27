import numpy as np
import torch
from captum.attr import LayerGradCam

from Utils.XAIUtils import XAIUtils


class GradCAM(XAIUtils):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


    # Pytorch

    def last_conv_layer_torch(self):
        layers = [l for l in self.model.children() if l._get_name().startswith('Conv')]
        last_layer = layers[-1] if layers else None

        return last_layer


    def heatmaps_torch(self, explainer, dataloader):
        explanations = []

        for inputs, labels in dataloader:
            targets = torch.argmax(self.model(inputs), dim=1)
            attrs = explainer.attribute(inputs, targets)
            explanations.append(attrs)

        explanations = torch.cat(explanations)
        return explanations.detach().numpy()


    def run_torch(self, file):
        last_conv_layer = self.last_conv_layer_torch()
        explainer = LayerGradCam(self.model, last_conv_layer)
        explanations = self.heatmaps_torch(explainer, self.data)
        np.save(file, explanations)


    # Tensorflow

    def run_tf(self):
        ...
