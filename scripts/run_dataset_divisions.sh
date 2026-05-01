#!/bin/bash

set -euo pipefail

EXTRA_ARGS=("$@")

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PXM_DIR="$SCRIPT_DIR/../../pxm-tools"
IDS_FILE="$SCRIPT_DIR/ids.json"
IDS_SUBSET="$SCRIPT_DIR/ids_subset.json"
IPS_SUBSET="$SCRIPT_DIR/ips_subset.json"
IPS_SUBSET_TXT="${IPS_SUBSET%.json}.txt"
IPS_ALL="$SCRIPT_DIR/ips_all.json"
IPS_ALL_TXT="${IPS_ALL%.json}.txt"

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

# --- One-time VM creation and setup ---
(cd "$PXM_DIR" && uv run pxm-create --config config-experiment.json --ids "$IDS_FILE")
(cd "$PXM_DIR" && uv run pxm-start --ids "$IDS_FILE" --ips "$IPS_ALL")

bash scripts/known_hosts.sh "$IPS_ALL_TXT"

bash scripts/run_commands.sh -i "$IPS_ALL_TXT" -f scripts/extend_disk.sh
echo "Waiting for VMs to reboot after disk extension..."
sleep 120

bash scripts/setup_vms.sh -f "$IPS_ALL_TXT"

# --- Machine benchmark ---
echo "=== Running machine benchmark on all VMs ==="
mkdir -p results/benchmark
bash scripts/run_machine_benchmark.sh "$IPS_ALL_TXT" results/benchmark

echo "=== Shutting down all VMs ==="
(cd "$PXM_DIR" && uv run pxm-stop --ids "$IDS_FILE")
# --------------------------------------

# Preprocess all datasets once — preprocessing is strategy- and node-count-independent
echo "=== Preprocessing all datasets ==="
for data_name in "${datasets[@]}"; do
    uv run flexfl-preprocess -d Benchmark --data_name "$data_name" -v 0.2 -t 0.2
done

for strategy in "${distributions[@]}"; do
    for n1 in "${atnog_test1[@]}"; do
        for n2 in "${hobbit[@]}"; do
            for n3 in "${samwise[@]}"; do
                total=$((n1 + n2 + n3))
                echo "=== distribution=$strategy  atnog-test1=$n1 hobbit=$n2 samwise=$n3 total=$total ==="

                python3 scripts/subset_ids.py \
                    --ids "$IDS_FILE" --output "$IDS_SUBSET" \
                    --atnog-test1 "$n1" --hobbit "$n2" --samwise "$n3"

                (cd "$PXM_DIR" && uv run pxm-start --ids "$IDS_SUBSET" --ips "$IPS_SUBSET")

                for data_name in "${datasets[@]}"; do
                    bash scripts/dataset_division.sh -d "$data_name" -n "$total" -s "$strategy" -p 0
                    bash scripts/send_dataset.sh -d "$data_name" -f "$IPS_SUBSET_TXT"
                    mkdir -p "results/atnog-test1_${n1}_hobbit_${n2}_samwise_${n3}/${data_name}"
                    cp -r "data/${data_name}" "results/atnog-test1_${n1}_hobbit_${n2}_samwise_${n3}/${data_name}/data"

                    for fl_algo in "${fl_algos[@]}"; do
                        bash scripts/run_commands.sh -i "$IPS_SUBSET_TXT" "rm -rf ~/flexfl/results"
                        bash scripts/run_on_vms.sh -f "$IPS_SUBSET_TXT" 0 0 \
                            --dataset Benchmark --data_name "$data_name" --nn benchmark \
                            --fl "$fl_algo" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
                        bash scripts/gather_results.sh \
                            -f "$IPS_SUBSET_TXT" \
                            -o "results/atnog-test1_${n1}_hobbit_${n2}_samwise_${n3}/${data_name}/${fl_algo}"
                    done

                    rm -rf "data/${data_name}"
                    bash scripts/run_commands.sh -i "$IPS_SUBSET_TXT" "rm -rf ~/flexfl/data/${data_name}"
                    bash scripts/run_commands.sh -i "$IPS_SUBSET_TXT" "rm -rf ~/flexfl/results"
                done

            done
        done
    done
done
