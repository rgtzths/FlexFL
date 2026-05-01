# FlexFL — Flexible Federated Learning Framework

Research framework for cost modelling of Federated Learning, supporting multiple algorithms, communication protocols, ML backends, and dataset partitioning strategies. Built for the PKDD 2026 paper.

## Requirements

- Python >= 3.12
- [`uv`](https://github.com/astral-sh/uv) (no prior installation step needed)

## CLI Commands

| Command | Purpose |
|---|---|
| `uv run flexfl` | Run federated learning training |
| `uv run flexfl-preprocess` | Download and preprocess a dataset |
| `uv run flexfl-division` | Partition a dataset across workers |
| `uv run flexfl-benchmark` | Benchmark the communication layer |
| `uv run flexfl-plot` | Post-experiment analysis and visualisation |
| `uv run flexfl-res` | Auto-restart a worker on failure |

All commands support `--help`. Available modules (algorithms, backends, datasets, neural nets) are discovered dynamically at runtime.

## Architecture

```
Master Node
├── FederatedABC      — FL algorithm (sync/async, centralized/decentralized)
├── MLFrameworkABC    — Training backend (Keras, PyTorch, TensorFlow)
├── DatasetABC        — Validation data + IID/non-IID split logic
├── WorkerManager     — Worker lifecycle, message routing, failure handling
└── CommABC           — Transport (Zenoh, MQTT, Kafka, MPI)

Worker Nodes
├── CommABC           — Receive/send model updates
├── MLFrameworkABC    — Local training
└── DatasetABC        — Training partition
```

## FL Algorithms

| Algorithm | Flag | Description |
|---|---|---|
| `CentralizedSync` | `--fl cs` | Server aggregation, synchronous |
| `CentralizedAsync` | `--fl ca` | Server aggregation, asynchronous |
| `DecentralizedSync` | `--fl ds` | Peer-to-peer, synchronous |
| `DecentralizedAsync` | `--fl da` | Peer-to-peer, asynchronous |

## Communication Protocols

| Protocol | Flag | Notes |
|---|---|---|
| `Zenoh` | `--comm Zenoh` | Default, no broker needed |
| `MQTT` | `--comm MQTT` | Requires broker (`requirements/mqtt-compose.yml`) |
| `Kafka` | `--comm Kafka` | Requires Kafka (`requirements/kafka-compose.yml`) |
| `MPI` | `--comm MPI` | HPC clusters via mpi4py |

## Datasets

Datasets load from HuggingFace (`inria-soda/tabular-benchmark`). Preprocess before training:

```bash
uv run flexfl-preprocess -d Benchmark --data_name clf_num_bank-marketing -v 0.2 -t 0.2
uv run flexfl-division   -d Benchmark --data_name clf_num_bank-marketing -n 8 -s iid
```

Division strategies (`-s`):

| Strategy | Description |
|---|---|
| `iid` | Equal random splits |
| `non_iid` | Majority-class assignment; `--distribution_percentage` controls skew |
| `dirichlet` | Dirichlet(α) sampling; lower α = more heterogeneous (default α=0.5) |

## Neural Networks

Neural nets live in `src/flexfl/neural_nets/`. The `Benchmark` class dynamically builds a network from the hyperparameter-optimised config in `results/hyperparameter_optimization/<data_name>.json`, making it the default net for all benchmark datasets.

All neural net model methods must accept `data_name` as their first argument:

```python
def keras_model(self, data_name, input_shape, output_size, is_classification): ...
```

## Full Experiment Pipeline

The complete experiment is automated by `scripts/run_dataset_divisions.sh`. Run from the `FlexFL/` directory after provisioning VMs with pxm-tools:

```bash
bash scripts/run_dataset_divisions.sh [extra_flexfl_args]
```

The script covers all combinations of node worker counts × distribution strategies × datasets × FL algorithms. Results are saved to:

```
results/atnog-test1_{n1}_hobbit_{n2}_samwise_{n3}/{dataset}/{fl_algo}/
```

## Individual Script Reference

All scripts accept a `-f <ips_file>` flag to target a custom set of VMs. Run from `FlexFL/`.

| Script | Usage |
|---|---|
| `scripts/setup_vms.sh` | `setup_vms.sh [-f <ips>]` — rsyncs FlexFL folder (excluding `data/`/`results/`), installs dependencies |
| `scripts/dataset_division.sh` | `dataset_division.sh -d <dataset> -n <workers> -s <strategy> [-p <0\|1>]` — `-p 0` skips preprocessing |
| `scripts/send_dataset.sh` | `send_dataset.sh -d <dataset> -f <ips>` |
| `scripts/run_on_vms.sh` | `run_on_vms.sh [-f <ips>] <interval> <chance> [args]` |
| `scripts/gather_results.sh` | `gather_results.sh [-f <ips>] [-o <output_dir>]` |
| `scripts/run_commands.sh` | `run_commands.sh [-v] [-w] [-i <ips>] -f <script>` or `run_commands.sh [-v] [-w] [-i <ips>] <command>` |
| `scripts/run_machine_benchmark.sh` | `run_machine_benchmark.sh [ips_file] [benchmark_args]` |
| `scripts/known_hosts.sh` | `known_hosts.sh [ips_file]` — rebuild local `~/.ssh/known_hosts` |

## VM Deployment

FlexFL is deployed to VMs via `rsync` (not installed from PyPI). `setup_vms.sh` rsyncs the local `FlexFL/` directory to `~/flexfl/` on each VM — excluding `data/` and `results/` to avoid resending experiment outputs — then runs `pip install .[all]` from it.

## Environment Variables

| Variable | Purpose |
|---|---|
| `KERAS_BACKEND` | Select Keras backend: `tensorflow`, `torch`, `jax` |
| `TF_CPP_MIN_LOG_LEVEL` | Suppress TensorFlow logs (set to `3`) |
| `VM_USERNAME`, `VM_PASSWORD` | SSH credentials for remote VMs (via `.env`) |
| `OMPI_COMM_WORLD_SIZE`, `OMPI_COMM_WORLD_RANK` | Set automatically when using MPI |
