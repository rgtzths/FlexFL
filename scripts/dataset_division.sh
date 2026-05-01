#!/bin/bash

usage() {
    echo "Usage: $0 -d <dataset> -n <workers> -s <distribution> [-p <0|1>]" >&2
    echo "  -p: run preprocessing step (1=yes, 0=skip; default: 1)" >&2
    echo "Example: $0 -d clf_num_bank-marketing -n 6 -s non_iid" >&2
}

dataset=""
workers=""
strategy=""
PREPROCESS=1

while getopts ":d:n:s:p:" opt; do
    case "$opt" in
        d) dataset="$OPTARG" ;;
        n) workers="$OPTARG" ;;
        s) strategy="$OPTARG" ;;
        p) PREPROCESS="$OPTARG" ;;
        *)
            usage
            exit 1
            ;;
    esac
done

if [[ -z "$dataset" || -z "$workers" || -z "$strategy" ]]; then
    usage
    exit 1
fi

echo "Running on dataset: $dataset"
if [[ "$PREPROCESS" -eq 1 ]]; then
    uv run flexfl-preprocess -d Benchmark --data_name "$dataset" -v 0.2 -t 0.2
fi
uv run flexfl-division -d Benchmark --data_name "$dataset" -n "$workers" -v 0 -t 0 -s "$strategy"
