import argparse
import json
import numpy as np
from pathlib import Path
from scipy.stats import pearsonr, spearmanr

CORR = {
    "pearson": pearsonr,
    "spearman": spearmanr
}

parser = argparse.ArgumentParser()
parser.add_argument('file1', help="Filename 1")
parser.add_argument('file2', help="Filename2")
parser.add_argument("-t", type=str, required=True, help="Problem type", choices=['tabular', 'image'])
parser.add_argument("-f", type=str, required=True, help="Correlations filename")
args = parser.parse_args()

Path("Results/Correlations").mkdir(parents=True, exist_ok=True)


def correlation_images():

    heatmaps1 = np.load(args.file1)
    heatmaps2 = np.load(args.file2)
    
    assert heatmaps1.shape == heatmaps2.shape, "Heatmaps must have the same shape"

    heatmaps1 = np.reshape(heatmaps1, (heatmaps1.shape[0], heatmaps1.shape[1] * heatmaps1.shape[2]))
    heatmaps2 = np.reshape(heatmaps2, (heatmaps2.shape[0], heatmaps2.shape[1] * heatmaps2.shape[2]))

    correlations = {}
    for corr_name, corr_fn in CORR.items():
        corrs = [corr_fn(heatmaps1[i], heatmaps2[i])[0] for i in range(len(heatmaps1))]
        correlations[corr_name] = np.mean(corrs)

    return correlations


def correlation_tabular():
    with open(args.file1, "r") as f1, open(args.file2, "r") as f2:
        importances1 = json.load(f1)
        importances2 = json.load(f2)

        assert importances1.keys() == importances2.keys(), "Features must be the same"

        importances1 = list(importances1.values())
        importances2 = list(importances2.values())

    correlations = {}
    for corr_name, corr_fn in CORR.items():
        correlations[corr_name] = corr_fn(importances1, importances2)[0]

    return correlations


if __name__ == "__main__":
    correlations = correlation_tabular() if args.t == "tabular" else correlation_images()
    
    with open(f"Results/Correlations/{args.f}.json", "w") as f:
        json.dump(correlations, f, indent=4)