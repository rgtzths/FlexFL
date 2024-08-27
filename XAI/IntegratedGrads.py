import numpy as np
import tensorflow as tf
import torch
from captum.attr import IntegratedGradients
from captum.attr import visualization as viz

from Utils.XAIUtils import XAIUtils


class IntegratedGrads(XAIUtils):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


    # Pytorch

    def heatmaps_torch(self, explainer, dataloader):        
        explanations = []

        for inputs, labels in dataloader:
            targets = torch.argmax(self.model(inputs), dim=1)
            attrs = explainer.attribute(inputs, inputs*0, targets)
            explanations.append(attrs)

        explanations = torch.cat(explanations)
        explanations = explanations.detach().numpy()

        if self.channels == 1:
            heatmaps = [viz._normalize_attr(exp, "absolute_value") for exp in explanations]
        else:
            heatmaps = []
            for exp in explanations:
                heatmap = np.transpose(exp, (1, 2, 0))
                heatmap = viz._normalize_attr(heatmap, "absolute_value", reduction_axis=2)
                heatmaps.append(heatmap)

        return np.array(heatmaps)


    def run_torch(self, file):
        explainer = IntegratedGradients(self.model)
        explanations = self.heatmaps_torch(explainer, self.data)
        np.save(file, explanations)



    # Tensorflow

    def get_gradients(self, img_input, top_pred_idx):
        img_input = tf.cast(img_input, tf.float32)

        with tf.GradientTape() as tape:
            tape.watch(img_input)
            preds = self.model(img_input)
            top_class = preds[:, top_pred_idx]

        grads = tape.gradient(top_class, img_input)
        return grads


    def gradients(self, img_input, baseline=None, num_steps=50):
        img_input = np.expand_dims(img_input, axis=0)
        top_pred_idx = np.argmax(self.model.predict(img_input, verbose=0))

        # Generate baseline image (all back)
        baseline = np.zeros(self.img_size).astype(np.float32)

        # Interpolation between baseline and input
        img_input = img_input.astype(np.float32)
        interpolated_image = [
            baseline + (step / num_steps) * (img_input - baseline)
            for step in range(num_steps + 1)
        ]
        interpolated_image = np.array(interpolated_image).astype(np.float32)

        # Calculate gradients for each interpolated image
        grads = []
        for img in interpolated_image:
            grad = self.get_gradients(img, top_pred_idx)
            grads.append(grad[0])
        grads = tf.convert_to_tensor(grads, dtype=tf.float32)

        # Approximate the integral using the trapezoidal rule
        grads = (grads[:-1] + grads[1:]) / 2.0
        avg_grads = tf.reduce_mean(grads, axis=0)

        # Calculate integrated gradients
        integrated_grads = (img_input - baseline) * avg_grads
        return integrated_grads.numpy()[0]
    

    def heatmaps_tf(self, img_input, baseline=None, num_steps=50):
        grads = self.gradients(img_input, baseline, num_steps)

        if len(self.img_size) == 2:
            heatmap = np.abs(grads)
        else:
            heatmap = np.sum(np.abs(grads), axis=-1)

        heatmap /= np.max(heatmap)
        return heatmap


    def run_tf(self, file):
        x_test, y_test = self.data
        self.img_size = x_test[0].shape

        explanations = []
        for sample in x_test[:10]:
            exp = self.heatmaps_tf(sample)
            explanations.append(exp)

        explanations = np.array(explanations)
        np.save(file, explanations)
