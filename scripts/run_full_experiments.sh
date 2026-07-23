#!/bin/bash

set -uo pipefail

EXTRA_ARGS=("$@")

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PXM_DIR="$SCRIPT_DIR/../../pxm-tools"
IDS_FILE="$SCRIPT_DIR/ids.json"
IDS_SUBSET="$SCRIPT_DIR/ids_subset.json"
IPS_SUBSET="$SCRIPT_DIR/ips_subset.json"
IPS_SUBSET_TXT="${IPS_SUBSET%.json}.txt"
IPS_ALL="$SCRIPT_DIR/ips_all.json"
IPS_ALL_TXT="${IPS_ALL%.json}.txt"

RESULTS_ROOT="results"
SETUP_MARKER="$RESULTS_ROOT/.setup_complete"
FAIL_LOG="$RESULTS_ROOT/_failures.log"

mkdir -p "$RESULTS_ROOT"

datasets=(
'clf_cat_albert'
'clf_cat_compas-two-years'
'clf_cat_covertype'
'clf_cat_default-of-credit-card-clients'
'clf_cat_electricity'
'clf_cat_eye_movements'
'clf_cat_road-safety'
'clf_num_Bioresponse'
'clf_num_Diabetes130US'
'clf_num_Higgs'
'clf_num_MagicTelescope'
'clf_num_MiniBooNE'
'clf_num_bank-marketing'
'clf_num_california'
'clf_num_covertype'
'clf_num_credit'
'clf_num_default-of-credit-card-clients'
'clf_num_electricity'
'clf_num_eye_movements'
'clf_num_heloc'
'clf_num_house_16H'
'clf_num_jannis'
'clf_num_pol'
'reg_cat_Airlines_DepDelay_1M'
'reg_cat_Allstate_Claims_Severity'
'reg_cat_Bike_Sharing_Demand'
'reg_cat_Brazilian_houses'
'reg_cat_Mercedes_Benz_Greener_Manufacturing'
'reg_cat_SGEMM_GPU_kernel_performance'
'reg_cat_abalone'
'reg_cat_analcatdata_supreme'
'reg_cat_delays_zurich_transport'
'reg_cat_diamonds'
'reg_cat_house_sales'
'reg_cat_medical_charges'
'reg_cat_nyc-taxi-green-dec-2016'
'reg_cat_particulate-matter-ukair-2017'
'reg_cat_seattlecrime6'
'reg_cat_topo_2_1'
'reg_cat_visualizing_soil'
'reg_num_Ailerons'
'reg_num_Bike_Sharing_Demand'
'reg_num_Brazilian_houses'
'reg_num_MiamiHousing2016'
'reg_num_abalone'
'reg_num_cpu_act'
'reg_num_delays_zurich_transport'
'reg_num_diamonds'
'reg_num_elevators'
'reg_num_house_16H'
'reg_num_house_sales'
'reg_num_houses'
'reg_num_medical_charges'
'reg_num_nyc-taxi-green-dec-2016'
'reg_num_pol'
'reg_num_sulfur'
'reg_num_superconduct'
'reg_num_wine_quality'
'reg_num_yprop_4_1'
)

atnog_test1=(2 4 8)
hobbit=(2 4 8 16)
samwise=(2 4 8 16 32)
distributions=(iid non_iid dirichlet)
fl_algos=(CentralizedSync CentralizedAsync DecentralizedSync DecentralizedAsync)

# Repeats per configuration (T10) — each config runs N times into distinct rep
# folders to estimate the target-noise floor. Override with FLEXFL_REPEATS.
REPEATS="${FLEXFL_REPEATS:-3}"

# Each repeat runs with a different model seed (data partition and HP vector stay
# fixed), so performance/comm targets — not just wall-clock time — carry per-config
# variance. Seeds are a fixed set indexed by repeat, so a resumed rep reuses its seed.
SEEDS=(42 43 44 45 46 47 48 49 50 51)

execute_fl_run() {
    local ips_file="$1" data_name="$2" fl_algo="$3" seed="$4" hp_args="$5"
    bash scripts/run_commands.sh -i "$ips_file" "rm -rf ~/flexfl/results"
    bash scripts/run_on_vms.sh -f "$ips_file" 0 0 \
        --dataset Benchmark --data_name "$data_name" --nn benchmark \
        --fl "$fl_algo" --seed "$seed" $hp_args "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
    run_rc=$?
}

source "$SCRIPT_DIR/_sweep_common.sh"
check_seeds_or_exit

# Optional diversity-tier restriction for a phased rollout (top 10 -> 20 -> all).
# Tiers are nested and chosen for meta-feature coverage first; the sweep is
# resumable, so expanding the tier just runs the newly-added datasets. Override
# with FLEXFL_TIER (10, 20, or all).
TIER="${FLEXFL_TIER:-all}"
if [ "$TIER" != "all" ]; then
    echo "=== Restricting to diversity tier: top ${TIER} datasets ==="
    mapfile -t datasets < <(printf '%s\n' "${datasets[@]}" | python3 scripts/select_dataset_tiers.py --tier "$TIER")
    if [ "${#datasets[@]}" -eq 0 ]; then
        echo "ERROR: tier selection for FLEXFL_TIER=${TIER} produced zero datasets; aborting." >&2
        exit 1
    fi
    echo "Active datasets (${#datasets[@]}): ${datasets[*]}"
fi

# --- One-time VM creation, setup, benchmark and preprocessing (idempotent) ---
if [ -f "$SETUP_MARKER" ]; then
    echo "=== Setup already complete ($SETUP_MARKER present) — skipping provisioning, benchmark and preprocessing ==="
else
    set -e  # fail-fast: setup must fully succeed before any experiment runs

    if [ -f "$IDS_FILE" ]; then
        echo "=== $IDS_FILE exists — VMs already created, skipping pxm-create ==="
    else
        (cd "$PXM_DIR" && uv run pxm-create --config config-experiment.json --ids "$IDS_FILE")
    fi
    (cd "$PXM_DIR" && uv run pxm-start --ids "$IDS_FILE" --ips "$IPS_ALL")

    bash scripts/known_hosts.sh "$IPS_ALL_TXT"

    bash scripts/run_commands.sh -i "$IPS_ALL_TXT" -f scripts/extend_disk.sh
    echo "Waiting for VMs to reboot after disk extension..."
    sleep 120

    bash scripts/setup_vms.sh -f "$IPS_ALL_TXT"

    # --- Machine benchmark ---
    # Reduced epochs/samples for a faster benchmark on the slow ARM VMs. Override with FLEXFL_BENCH_ARGS.
    BENCH_ARGS="${FLEXFL_BENCH_ARGS:---epochs 25 --warmup-epochs 5 --repeats 3 --samples 10000}"
    echo "=== Running machine benchmark on all VMs ($BENCH_ARGS) ==="
    mkdir -p results/benchmark
    bash scripts/run_machine_benchmark.sh "$IDS_FILE" "$IPS_ALL" results/benchmark $BENCH_ARGS

    echo "=== Shutting down all VMs ==="
    (cd "$PXM_DIR" && uv run pxm-stop --ids "$IDS_FILE")

    # Datasets are preprocessed on demand inside the sweep (once per dataset,
    # cached in data/<name>/_data), so a phased tier rollout only preprocesses
    # what it runs and a resume survives the per-dataset partition cleanup.

    set +e
    touch "$SETUP_MARKER"
    echo "=== Setup complete ==="
fi

run_sweep

echo "=== Sweep complete. ==="
if [ -s "$FAIL_LOG" ]; then
    echo "Some steps failed and were skipped — see $FAIL_LOG ($(wc -l < "$FAIL_LOG") entries). Re-run this script to retry them; completed runs are skipped."
fi
