import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Create a subset ids.json by taking the first n IDs from each node.")
    parser.add_argument("--ids", type=Path, required=True, help="Path to the source ids.json")
    parser.add_argument("--output", type=Path, required=True, help="Path to write the subset ids.json")
    parser.add_argument("--atnog-test1", type=int, required=True, dest="atnog_test1", help="Number of VMs to select from atnog-test1")
    parser.add_argument("--hobbit", type=int, required=True, help="Number of VMs to select from hobbit")
    parser.add_argument("--samwise", type=int, required=True, help="Number of VMs to select from samwise")
    args = parser.parse_args()

    with open(args.ids) as f:
        ids = json.load(f)

    subset = {"frodo": ids["frodo"]}
    for node, count in [("atnog-test1", args.atnog_test1), ("hobbit", args.hobbit), ("samwise", args.samwise)]:
        subset[node] = {"api": ids[node]["api"], "ids": ids[node]["ids"][:count]}

    with open(args.output, "w") as f:
        json.dump(subset, f, indent=2)


if __name__ == "__main__":
    main()
