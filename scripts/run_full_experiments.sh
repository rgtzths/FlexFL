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

SETUP_MARKER="results/.setup_complete"
FAIL_LOG="results/_failures.log"

mkdir -p results

# Record a failed step (does not abort the sweep). Uses the loop vars in scope.
log_failure() {
    echo "$(date -u +%FT%TZ)  FAILED  step=$1  strategy=${strategy:-}  nodes=${n1:-}_${n2:-}_${n3:-}  dataset=${data_name:-}  fl=${fl_algo:-}" >> "$FAIL_LOG"
    echo "  ! recorded failure: step=$1 (${strategy:-}/${n1:-}_${n2:-}_${n3:-}/${data_name:-}/${fl_algo:-})" >&2
}

# A run is "done" only when it wrote a success sentinel (see run_on_vms.sh /
# run_output_complete). This is the completion gate consumed by the resume logic
# and by the meta-dataset assembler (T11), which must exclude non-_SUCCESS runs.
is_done() {
    local d="$1"
    [ -f "$d/_SUCCESS" ]
}

# True when gathered output holds a master log with a terminal 'end' event —
# the authoritative "this run finished cleanly" check, run against the local copy.
run_output_complete() {
    local d="$1" f
    f="$(find "$d" -name 'log_0.jsonl' 2>/dev/null | head -n 1)"
    [ -n "$f" ] && grep -q '"event": "end"' "$f"
}

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
if [ "$REPEATS" -gt "${#SEEDS[@]}" ]; then
    echo "FLEXFL_REPEATS=$REPEATS exceeds the ${#SEEDS[@]} predefined seeds in SEEDS — add more." >&2
    exit 1
fi

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

    # Verify every VM actually built the flexfl venv. setup_vms.sh exits 0 even when a
    # VM's vm.sh failed, so a silently-broken worker would later hang the master in
    # wait_for_workers. Retry setup on any VM still missing the venv; abort if it
    # persists rather than starting the sweep with a doomed worker.
    _vm_user="$(grep -E '^VM_USERNAME=' "$SCRIPT_DIR/../.env" | cut -d= -f2-)"
    _ssh_key="$SCRIPT_DIR/../keys/id_rsa"
    list_missing_venvs() {
        local ip
        while read -r ip; do
            [[ -z "$ip" || "$ip" =~ ^# ]] && continue
            ssh -i "$_ssh_key" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
                -o ConnectTimeout=10 -o BatchMode=yes -q "$_vm_user@$ip" 'test -f ~/flexfl/venv/bin/flexfl' 2>/dev/null \
                || echo "$ip"
        done < "$IPS_ALL_TXT"
    }
    for _attempt in 1 2 3; do
        mapfile -t _missing < <(list_missing_venvs)
        [ "${#_missing[@]}" -eq 0 ] && break
        echo "=== venv missing on ${#_missing[@]} VM(s): ${_missing[*]} — retry setup (attempt $_attempt) ==="
        printf '%s\n' "${_missing[@]}" > "$SCRIPT_DIR/ips_retry.txt"
        export SSHPASS="$(grep -E '^VM_PASSWORD=' "$SCRIPT_DIR/../.env" | cut -d= -f2-)"
        for _ip in "${_missing[@]}"; do
            sshpass -e ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q \
                "$_vm_user@$_ip" "cloud-init status --wait >/dev/null 2>&1; sudo dpkg --configure -a >/dev/null 2>&1 || true" &
        done
        wait
        unset SSHPASS
        bash scripts/setup_vms.sh -f "$SCRIPT_DIR/ips_retry.txt"
    done
    mapfile -t _missing < <(list_missing_venvs)
    if [ "${#_missing[@]}" -ne 0 ]; then
        echo "ERROR: flexfl venv still missing on ${_missing[*]} after 3 setup attempts — aborting." >&2
        exit 1
    fi
    echo "=== venv verified on all $(wc -l < "$IPS_ALL_TXT") VMs ==="

    # --- Machine benchmark ---
    echo "=== Running machine benchmark on all VMs ==="
    mkdir -p results/benchmark
    bash scripts/run_machine_benchmark.sh "$IDS_FILE" "$IPS_ALL" results/benchmark

    echo "=== Shutting down all VMs ==="
    (cd "$PXM_DIR" && uv run pxm-stop --ids "$IDS_FILE")

    # Datasets are preprocessed on demand inside the sweep (once per dataset,
    # cached in data/<name>/_data), so a phased tier rollout only preprocesses
    # what it runs and a resume survives the per-dataset partition cleanup.

    set +e
    touch "$SETUP_MARKER"
    echo "=== Setup complete ==="
fi

# --- Sweep (fault-tolerant, resumable) ---
for strategy in "${distributions[@]}"; do
    for n1 in "${atnog_test1[@]}"; do
        for n2 in "${hobbit[@]}"; do
            for n3 in "${samwise[@]}"; do
                total=$((n1 + n2 + n3))
                combo="atnog-test1_${n1}_hobbit_${n2}_samwise_${n3}"
                # Strategy MUST be in the path: the same node-combo is swept under all
                # three distributions, so without this segment their result dirs collide
                # and resume would skip non_iid/dirichlet after iid completes.
                run_root="results/${strategy}/${combo}"
                echo "=== distribution=$strategy  atnog-test1=$n1 hobbit=$n2 samwise=$n3 total=$total ==="

                if ! python3 scripts/subset_ids.py \
                    --ids "$IDS_FILE" --output "$IDS_SUBSET" \
                    --atnog-test1 "$n1" --hobbit "$n2" --samwise "$n3"; then
                    log_failure "subset_ids"
                    continue
                fi

                if ! (cd "$PXM_DIR" && uv run pxm-start --ids "$IDS_SUBSET" --ips "$IPS_SUBSET"); then
                    log_failure "pxm-start-subset"
                    continue
                fi

                # Record the participating VMs for this (strategy, combo) so the
                # meta-dataset assembler (T11) can join worker compute profiles from
                # results/benchmark/. Line 1 is the anchor (frodo); the rest are workers.
                # Each line is "<ip> <node> <vmid>".
                mkdir -p "$run_root"
                if ! python3 scripts/vm_identity.py --ids "$IDS_SUBSET" --ips "$IPS_SUBSET" --out "$run_root/workers.txt"; then
                    log_failure "vm_identity"
                    continue
                fi

                for data_name in "${datasets[@]}"; do
                    base="${run_root}/${data_name}"

                    # Skip the whole dataset if every algo × every repeat under this
                    # node-combo is already done.
                    all_done=1
                    for fl_algo in "${fl_algos[@]}"; do
                        for r in $(seq 1 "$REPEATS"); do
                            is_done "${base}/${fl_algo}/rep_${r}" || { all_done=0; break 2; }
                        done
                    done
                    fl_algo=""; r=""
                    if [ "$all_done" -eq 1 ]; then
                        echo "  - ${combo}/${data_name}: all algos done, skipping"
                        continue
                    fi

                    mkdir -p "$base"
                    # Preprocess on demand: only if this dataset's _data cache is absent
                    # (first time seen, or after a resume that cleared it). Preprocessing
                    # is strategy- and node-count-independent, so it runs once per dataset.
                    pflag=0
                    [ -f "data/${data_name}/_data/x_train.npy" ] || pflag=1
                    if ! bash scripts/dataset_division.sh -d "$data_name" -n "$total" -s "$strategy" -p "$pflag"; then
                        log_failure "dataset_division"
                        continue
                    fi
                    if ! bash scripts/send_dataset.sh -d "$data_name" -f "$IPS_SUBSET_TXT"; then
                        log_failure "send_dataset"
                        continue
                    fi
                    # Record the partition recipe instead of copying the (large) split
                    # data into results/ — copies accumulated unbounded over ~60 combos ×
                    # ~59 datasets. The division is fully deterministic given these
                    # parameters (preprocess train_test_split random_state=42; array_split;
                    # dirichlet seed=42), so the recipe is sufficient to reproduce it.
                    rm -rf "${base}/data"
                    cat > "${base}/division.json" <<EOF
{
  "dataset": "${data_name}",
  "num_workers": ${total},
  "nodes": {"atnog-test1": ${n1}, "hobbit": ${n2}, "samwise": ${n3}},
  "strategy": "${strategy}",
  "val_size": 0,
  "test_size": 0,
  "distribution_percentage": 0.9,
  "alpha": 0.5,
  "seed": 42,
  "preprocess": {"val_size": 0.2, "test_size": 0.2}
}
EOF
                    # Cross-worker feature entropy meta-features (T08): computed now, while
                    # the node_* partitions still exist, and merged into division.json.
                    # Non-fatal — a missing entropy just leaves those columns absent.
                    uv run python scripts/compute_partition_entropy.py \
                        --data-dir "data/${data_name}" --num-workers "$total" \
                        --update-json "${base}/division.json" \
                        || echo "  ! entropy computation failed for ${data_name} (continuing)" >&2

                    for fl_algo in "${fl_algos[@]}"; do
                        # Same HP vector across all repeats of this config (key omits the
                        # repeat index) — a repeat is a noise sample, not a new config.
                        hp_args=$(python3 scripts/sample_hyperparameters.py \
                            --algo "$fl_algo" --key "${combo}|${data_name}|${fl_algo}" \
                            --json-out "${base}/.hp_${fl_algo}.json")

                        for r in $(seq 1 "$REPEATS"); do
                            seed="${SEEDS[$((r - 1))]}"
                            run_dir="${base}/${fl_algo}/rep_${r}"
                            if is_done "$run_dir"; then
                                echo "    - ${fl_algo} rep ${r}: done, skipping"
                                continue
                            fi
                            # Fresh attempt: discard any partial/failed output from a prior try.
                            rm -rf "$run_dir"
                            bash scripts/run_commands.sh -i "$IPS_SUBSET_TXT" "rm -rf ~/flexfl/results"

                            bash scripts/run_on_vms.sh -f "$IPS_SUBSET_TXT" 0 0 \
                                --dataset Benchmark --data_name "$data_name" --nn benchmark \
                                --fl "$fl_algo" --seed "$seed" $hp_args "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
                            run_rc=$?

                            # Gather regardless of outcome so a completed run's logs — and
                            # partial logs on failure — are kept locally for the sentinel
                            # check and for diagnosis.
                            bash scripts/gather_results.sh -f "$IPS_SUBSET_TXT" -o "$run_dir"

                            if [ "$run_rc" -eq 0 ] && run_output_complete "$run_dir"; then
                                cp -f "${base}/.hp_${fl_algo}.json" "$run_dir/hyperparameters.json"
                                touch "$run_dir/_SUCCESS"
                                echo "    - ${fl_algo} rep ${r}: success"
                            else
                                touch "$run_dir/_FAILED"
                                log_failure "run_on_vms"
                                echo "    - ${fl_algo} rep ${r}: FAILED (marked _FAILED, will retry on re-run)"
                            fi
                        done
                        rm -f "${base}/.hp_${fl_algo}.json"
                    done
                    fl_algo=""; r=""

                    # Drop the large per-worker partitions but keep data/<name>/_data
                    # so the next combo reuses the preprocessed cache (no re-download).
                    rm -rf "data/${data_name}"/node_*
                    bash scripts/run_commands.sh -i "$IPS_SUBSET_TXT" "rm -rf ~/flexfl/data/${data_name}"
                    bash scripts/run_commands.sh -i "$IPS_SUBSET_TXT" "rm -rf ~/flexfl/results"
                done

            done
        done
    done
done

echo "=== Sweep complete. ==="
if [ -s "$FAIL_LOG" ]; then
    echo "Some steps failed and were skipped — see $FAIL_LOG ($(wc -l < "$FAIL_LOG") entries). Re-run this script to retry them; completed runs are skipped."
fi
