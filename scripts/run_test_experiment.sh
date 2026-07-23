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
IDS_FILE="$SCRIPT_DIR/ids_test.json"
IDS_SUBSET="$SCRIPT_DIR/ids_subset_test.json"
IPS_SUBSET="$SCRIPT_DIR/ips_subset_test.json"
IPS_SUBSET_TXT="${IPS_SUBSET%.json}.txt"
IPS_ALL="$SCRIPT_DIR/ips_all_test.json"
IPS_ALL_TXT="${IPS_ALL%.json}.txt"
RESULTS_ROOT="results/test"
SETUP_MARKER="$RESULTS_ROOT/.setup_complete"
FAIL_LOG="$RESULTS_ROOT/_failures.log"

mkdir -p "$RESULTS_ROOT"

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

execute_fl_run() {
    local ips_file="$1" data_name="$2" fl_algo="$3" seed="$4" hp_args="$5"
    # Kill any stale flexfl/screens from a prior (possibly timed-out) run so
    # a fresh run starts clean, then clear remote results.
    bash scripts/run_commands.sh -i "$ips_file" "pkill -f flexfl 2>/dev/null; screen -wipe >/dev/null 2>&1; rm -rf ~/flexfl/results"

    # Cap wall-clock: a stuck run (a worker that never joins, a comm stall)
    # otherwise hangs the sweep forever on the master-wait.
    timeout "$RUN_TIMEOUT" bash scripts/run_on_vms.sh -f "$ips_file" 0 0 \
        --dataset Benchmark --data_name "$data_name" --nn benchmark \
        --fl "$fl_algo" --seed "$seed" $hp_args "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
    run_rc=$?
    if [ "$run_rc" -eq 124 ]; then
        echo "    ! ${fl_algo}: TIMED OUT after ${RUN_TIMEOUT}s — killing stale flexfl" >&2
        bash scripts/run_commands.sh -i "$ips_file" "pkill -f flexfl 2>/dev/null; screen -wipe >/dev/null 2>&1 || true"
    fi
}

source "$SCRIPT_DIR/_sweep_common.sh"
check_seeds_or_exit

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
    mkdir -p "$RESULTS_ROOT/benchmark"
    bash scripts/run_machine_benchmark.sh "$IDS_FILE" "$IPS_ALL" "$RESULTS_ROOT/benchmark" $BENCH_ARGS

    echo "=== Shutting down all VMs ==="
    (cd "$PXM_DIR" && uv run pxm-stop --ids "$IDS_FILE")

    set +e
    touch "$SETUP_MARKER"
    echo "=== Setup complete ==="
fi

run_sweep

echo "=== Test sweep complete. Shutting down all test VMs ==="
(cd "$PXM_DIR" && uv run pxm-stop --ids "$IDS_FILE") || echo "  ! pxm-stop failed — VMs may still be running" >&2

if [ -s "$FAIL_LOG" ]; then
    echo "Some steps failed and were skipped — see $FAIL_LOG ($(wc -l < "$FAIL_LOG") entries). Re-run this script to retry them; completed runs are skipped."
fi

echo "=== Verifying acceptance criteria ==="
verify_ok=1

expected_success=$(( ${#distributions[@]} * ${#datasets[@]} * ${#fl_algos[@]} * REPEATS ))
strategy_dirs=()
for d in "${distributions[@]}"; do strategy_dirs+=("$RESULTS_ROOT/$d"); done
success_count=$(find "${strategy_dirs[@]}" -name _SUCCESS 2>/dev/null | wc -l)
if [ "$success_count" -eq "$expected_success" ]; then
    echo "  - _SUCCESS count: $success_count/$expected_success OK"
else
    echo "  ! _SUCCESS count: $success_count/$expected_success MISMATCH" >&2
    verify_ok=0
fi

bench_files=("$RESULTS_ROOT"/benchmark/machine_benchmark_*.json)
bench_count=0
[ -e "${bench_files[0]}" ] && bench_count="${#bench_files[@]}"
if [ "$bench_count" -eq 7 ]; then
    for f in "${bench_files[@]}"; do
        python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
models = d.get('results', {})
ok = bool(models) and all(
    isinstance(m.get('avg_epochs_per_second'), (int, float)) and m['avg_epochs_per_second'] == m['avg_epochs_per_second']
    and abs(m['avg_epochs_per_second']) != float('inf')
    for m in models.values()
)
sys.exit(0 if ok else 1)
" "$f" || { echo "  ! $f: avg_epochs_per_second missing or not finite for some model" >&2; verify_ok=0; }
    done
    [ "$verify_ok" -eq 1 ] && echo "  - benchmark JSONs: $bench_count/7, all finite rates OK"
else
    echo "  ! benchmark JSON count: $bench_count/7 MISMATCH" >&2
    verify_ok=0
fi

assemble_out=$(uv run python scripts/assemble_meta_dataset.py --results-dir "$RESULTS_ROOT" --out "$RESULTS_ROOT/meta_dataset.csv" 2>&1)
assemble_rc=$?
echo "$assemble_out"
if [ "$assemble_rc" -eq 0 ]; then
    skipped=$(echo "$assemble_out" | grep -oE '\([0-9]+ skipped\)' | grep -oE '[0-9]+' | tail -1)
    skipped="${skipped:-0}"
    row_count=$(($(wc -l < "$RESULTS_ROOT/meta_dataset.csv") - 1))
    empty_cols=$(python3 -c "
import csv, sys
with open(sys.argv[1]) as f:
    reader = csv.reader(f)
    header = next(reader)
    rows = list(reader)
has_value = [False] * len(header)
for row in rows:
    for i, v in enumerate(row):
        if v.strip():
            has_value[i] = True
print(','.join(header[i] for i, v in enumerate(has_value) if not v))
" "$RESULTS_ROOT/meta_dataset.csv")
    if [ "$row_count" -eq "$expected_success" ] && [ -z "$empty_cols" ]; then
        echo "  - meta_dataset.csv: $row_count rows (warnings reported: $skipped), no empty columns OK"
    else
        echo "  ! meta_dataset.csv: $row_count rows (expected $expected_success), empty columns: [${empty_cols:-none}]" >&2
        verify_ok=0
    fi
else
    echo "  ! assemble_meta_dataset.py failed (rc=$assemble_rc)" >&2
    verify_ok=0
fi

if [ "$verify_ok" -eq 1 ]; then
    echo "=== ALL ACCEPTANCE CRITERIA PASSED ==="
else
    echo "=== ACCEPTANCE CRITERIA FAILED — see markers above ===" >&2
fi

if [ "$verify_ok" -eq 1 ] && { [ ! -s "$FAIL_LOG" ]; }; then
    echo "=== Cleaning up test state (all checks passed) ==="
    rm -rf "$RESULTS_ROOT" "$IDS_FILE" "$IPS_ALL" "$IPS_ALL_TXT" \
           "$IDS_SUBSET" "$IPS_SUBSET" "$IPS_SUBSET_TXT" "$SCRIPT_DIR/ips_retry.txt"
    rm -f "$PXM_DIR/$TEST_CONFIG"
else
    echo "=== Leaving test state in place for debugging (see $FAIL_LOG / verification output above) ===" >&2
fi
