import numpy as np
import pandas as pd
from permetrics import ClassificationMetric
from sklearn.metrics import confusion_matrix
from sklearn.metrics import matthews_corrcoef


def mcc(y_true, y_pred):
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    return (tp * tn - fp * fn) / np.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))

y_preds = pd.read_csv("temp/preds.txt", header=None).values.astype(int)
y_true = pd.read_csv("temp/y.txt", header=None).values.astype(int)

# n_samples = 250000
# y_preds = y_preds[:n_samples]
# y_true = y_true[:n_samples]

print(matthews_corrcoef(y_true, y_preds))

# print(y_preds.shape, y_true.shape)

# evaluator = ClassificationMetric(y_true, y_preds)

# mcc_ = evaluator.get_metric_by_name("MCC")
# print(mcc_)  

# print(y_preds.shape, y_true.shape)
# mcc_ = mcc(y_true, y_preds)
# print(mcc_)

# print("5 fold")
# total = 0
# for i in range(5):
#     y_p = y_preds[i*50000:(i+1)*50000]
#     y_t = y_true[i*50000:(i+1)*50000]
#     mcc_ = mcc(y_t, y_p)
#     print(mcc_)
#     total += mcc_

# print("Average")
# print(total/5)
