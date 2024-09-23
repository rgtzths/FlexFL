import argparse
from pathlib import Path

from config import DATASETS, ML, MODELS, XAI

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--dataset", type=str, required=True, help="Dataset name", choices=DATASETS.keys())
parser.add_argument("--ml", type=str, required=True, help="ML framework", choices=ML.keys())
parser.add_argument("-m", "--model", type=str, required=True, help="Model name")
parser.add_argument("-p", "--path", type=str, required=True, help="Model path")
parser.add_argument("-x", type=str, required=True, help="XAI technique")
parser.add_argument("-b", "--batchsize", type=int, required=False, default=64, help="Batch size")
args = parser.parse_args()

Path("Results/XAI").mkdir(parents=True, exist_ok=True)

dataset = DATASETS[args.dataset]()
model = MODELS[args.model]()

explanations_filename = f"Results/XAI/{args.path.split("/")[-1].split(".")[0]}_{args.ml}_{args.x}"
explainer = XAI[args.x](dataset=dataset, ml=args.ml, model=model, model_path=args.path, batch_size=args.batchsize)

explainer.run(explanations_filename)