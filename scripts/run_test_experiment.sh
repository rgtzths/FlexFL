#!/bin/bash

# Reduced end-to-end test orchestrator (T32). Mirrors run_full_experiments.sh — same
# setup/benchmark/sweep/resume/gather/_SUCCESS logic — scaled down to validate the fixed
# pipeline before the full campaign:
#   - 7 VMs (frodo anchor + atnog-test1/hobbit/samwise = 2 each) via a generated reduced
#     pxm config (config-test.json, derived from config-experiment.json).
#   - node combo 2/2/2 only; distributions iid + non_iid; 2 small datasets; all 4 FL algos;
#     REPEATS default 1; --epochs passed through EXTRA_ARGS; extend_disk skipped.

set -uo pipefail

EXTRA_ARGS=("$@")

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PXM_DIR="${FLEXFL_PXM_DIR:-$SCRIPT_DIR/../../pxm-tools}"
TEST_CONFIG="config-test.json"   # relative to PXM_DIR; generated below
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

is_done() {
    local d="$1"
    [ -f "$d/_SUCCESS" ]
}

run_output_complete() {
    local d="$1" f
    f="$(find "$d" -name 'log_0.jsonl' 2>/dev/null | head -n 1)"
    [ -n "$f" ] && grep -q '"event": "end"' "$f"
}

# --- Reduced test matrix ---
datasets=(
'clf_cat_compas-two-years'
'reg_cat_abalone'
)

atnog_test1=(2)
hobbit=(2)
samwise=(2)
distributions=(iid non_iid)
fl_algos=(CentralizedSync CentralizedAsync DecentralizedSync DecentralizedAsync)

REPEATS="${FLEXFL_REPEATS:-1}"
RUN_TIMEOUT="${FLEXFL_RUN_TIMEOUT:-900}"   # per-run wall-clock cap (s); a hung run is marked _FAILED and the sweep continues
# Reduced machine-benchmark workload: enough to measure a compute rate and validate the
# feature path, kept to a few minutes even on the slow ARM VMs (the full 50-epoch default
# takes ~2h). Override with FLEXFL_BENCH_ARGS.
BENCH_ARGS="${FLEXFL_BENCH_ARGS:---epochs 3 --warmup-epochs 1 --repeats 1 --samples 2000}"

SEEDS=(42 43 44 45 46 47 48 49 50 51)
if [ "$REPEATS" -gt "${#SEEDS[@]}" ]; then
    echo "FLEXFL_REPEATS=$REPEATS exceeds the ${#SEEDS[@]} predefined seeds in SEEDS — add more." >&2
    exit 1
fi

# --- One-time VM creation, setup and benchmark (idempotent) ---
if [ -f "$SETUP_MARKER" ]; then
    echo "=== Setup already complete ($SETUP_MARKER present) — skipping provisioning and benchmark ==="
else
    set -e  # fail-fast: setup must fully succeed before any experiment runs

    # Generate the reduced pxm config (frodo-first, n_vms 2/2/2/1) from the campaign config.
    echo "=== Generating reduced pxm config ($TEST_CONFIG) ==="
    python3 - "$PXM_DIR/config-experiment.json" "$PXM_DIR/$TEST_CONFIG" <<'PYEOF'
import json, sys
src_path, out_path = sys.argv[1], sys.argv[2]
with open(src_path) as f:
    src = json.load(f)
counts = {"frodo": 1, "atnog-test1": 2, "hobbit": 2, "samwise": 2}
by_node = {c["node"]: c for c in src["vm_configs"]}
missing = [n for n in counts if n not in by_node]
if missing:
    sys.exit(f"config-experiment.json missing node(s): {missing}")
out = {"prefix": src["prefix"], "vm_configs": []}
for node in ["frodo", "atnog-test1", "hobbit", "samwise"]:
    c = by_node[node]
    c["vms"][0]["n_vms"] = counts[node]
    out["vm_configs"].append(c)
with open(out_path, "w") as f:
    json.dump(out, f, indent=4)
print(f"wrote {out_path}: " + ", ".join(f"{n}={counts[n]}" for n in counts))
PYEOF

    if [ -f "$IDS_FILE" ]; then
        echo "=== $IDS_FILE exists — VMs already created, skipping pxm-create ==="
    else
        (cd "$PXM_DIR" && uv run pxm-create --config "$TEST_CONFIG" --ids "$IDS_FILE")
    fi
    (cd "$PXM_DIR" && uv run pxm-start --ids "$IDS_FILE" --ips "$IPS_ALL")

    bash scripts/known_hosts.sh "$IPS_ALL_TXT"

    # extend_disk skipped (reduced run needs little disk). Without its reboot the VMs
    # are on first boot, so wait for cloud-init to finish before setup_vms — otherwise
    # vm.sh's apt steps race cloud-init for the dpkg lock and the venv is never built.
    echo "=== Waiting for cloud-init to complete on all VMs ==="
    _vm_user="$(grep -E '^VM_USERNAME=' "$SCRIPT_DIR/../.env" | cut -d= -f2-)"
    export SSHPASS="$(grep -E '^VM_PASSWORD=' "$SCRIPT_DIR/../.env" | cut -d= -f2-)"
    while read -r _ip; do
        [[ -z "$_ip" || "$_ip" =~ ^# ]] && continue
        sshpass -e ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q \
            "$_vm_user@$_ip" "cloud-init status --wait >/dev/null 2>&1; sudo dpkg --configure -a >/dev/null 2>&1 || true" &
    done < "$IPS_ALL_TXT"
    wait
    unset SSHPASS

    bash scripts/setup_vms.sh -f "$IPS_ALL_TXT"

    # Verify every VM actually built the flexfl venv. setup_vms.sh exits 0 even when a
    # VM's vm.sh failed, so a silently-broken worker would later hang the master in
    # wait_for_workers. Retry setup on any VM still missing the venv; abort if it
    # persists rather than starting the sweep with a doomed worker.
    _ssh_key="$SCRIPT_DIR/../keys/id_rsa"
    list_missing_venvs() {
        local ip
        while read -r ip; do
            [[ -z "$ip" || "$ip" =~ ^# ]] && continue
            ssh -i "$_ssh_key" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
                -o ConnectTimeout=10 -q "$_vm_user@$ip" 'test -f ~/flexfl/venv/bin/flexfl' 2>/dev/null \
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
    echo "=== Running machine benchmark on all VMs ($BENCH_ARGS) ==="
    mkdir -p results/benchmark
    bash scripts/run_machine_benchmark.sh "$IDS_FILE" "$IPS_ALL" results/benchmark $BENCH_ARGS

    echo "=== Shutting down all VMs ==="
    (cd "$PXM_DIR" && uv run pxm-stop --ids "$IDS_FILE")

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

                mkdir -p "$run_root"
                if ! python3 scripts/vm_identity.py --ids "$IDS_SUBSET" --ips "$IPS_SUBSET" --out "$run_root/workers.txt"; then
                    log_failure "vm_identity"
                    continue
                fi

                for data_name in "${datasets[@]}"; do
                    base="${run_root}/${data_name}"

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
                    uv run python scripts/compute_partition_entropy.py \
                        --data-dir "data/${data_name}" --num-workers "$total" \
                        --update-json "${base}/division.json" \
                        || echo "  ! entropy computation failed for ${data_name} (continuing)" >&2

                    for fl_algo in "${fl_algos[@]}"; do
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
                            rm -rf "$run_dir"
                            # Kill any stale flexfl/screens from a prior (possibly timed-out) run so
                            # a fresh run starts clean, then clear remote results.
                            bash scripts/run_commands.sh -i "$IPS_SUBSET_TXT" "pkill -f flexfl 2>/dev/null; screen -wipe >/dev/null 2>&1; rm -rf ~/flexfl/results"

                            # Cap wall-clock: a stuck run (a worker that never joins, a comm stall)
                            # otherwise hangs the sweep forever on the master-wait.
                            timeout "$RUN_TIMEOUT" bash scripts/run_on_vms.sh -f "$IPS_SUBSET_TXT" 0 0 \
                                --dataset Benchmark --data_name "$data_name" --nn benchmark \
                                --fl "$fl_algo" --seed "$seed" $hp_args "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
                            run_rc=$?
                            if [ "$run_rc" -eq 124 ]; then
                                echo "    ! ${fl_algo} rep ${r}: TIMED OUT after ${RUN_TIMEOUT}s — killing stale flexfl" >&2
                                bash scripts/run_commands.sh -i "$IPS_SUBSET_TXT" "pkill -f flexfl 2>/dev/null; screen -wipe >/dev/null 2>&1 || true"
                            fi

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

                    rm -rf "data/${data_name}"/node_*
                    bash scripts/run_commands.sh -i "$IPS_SUBSET_TXT" "rm -rf ~/flexfl/data/${data_name}"
                    bash scripts/run_commands.sh -i "$IPS_SUBSET_TXT" "rm -rf ~/flexfl/results"
                done

            done
        done
    done
done

echo "=== Test sweep complete. Shutting down all test VMs ==="
(cd "$PXM_DIR" && uv run pxm-stop --ids "$IDS_FILE") || echo "  ! pxm-stop failed — VMs may still be running" >&2

if [ -s "$FAIL_LOG" ]; then
    echo "Some steps failed and were skipped — see $FAIL_LOG ($(wc -l < "$FAIL_LOG") entries). Re-run this script to retry them; completed runs are skipped."
fi
