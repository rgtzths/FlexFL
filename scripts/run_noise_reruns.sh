#!/bin/bash

set -uo pipefail

EXTRA_ARGS=("$@")

if [ -z "${FLEXFL_NOISE_LIST:-}" ] || [ -z "${FLEXFL_NOISE_ROOT:-}" ]; then
    echo "FLEXFL_NOISE_LIST and FLEXFL_NOISE_ROOT must both be set." >&2
    exit 2
fi
if ! realpath -m / > /dev/null 2>&1; then
    echo "realpath -m is unavailable on this host; cannot resolve FLEXFL_NOISE_LIST and FLEXFL_NOISE_ROOT." >&2
    exit 2
fi
CONFIG_LIST="$(realpath -m "$FLEXFL_NOISE_LIST")" || exit 2
RESULTS_ROOT="$(realpath -m "$FLEXFL_NOISE_ROOT")" || exit 2

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.." || exit 2
REPO_DIR="$(pwd -P)"
PXM_DIR="${FLEXFL_PXM_DIR:-$SCRIPT_DIR/../../pxm-tools}"
IDS_FILE="${FLEXFL_NOISE_IDS_FILE:-$SCRIPT_DIR/ids.json}"
IDS_SUBSET="$SCRIPT_DIR/ids_subset_noise.json"
IPS_SUBSET="$SCRIPT_DIR/ips_subset_noise.json"
IPS_SUBSET_TXT="${IPS_SUBSET%.json}.txt"
FAIL_LOG="$RESULTS_ROOT/_failures.log"

source "$SCRIPT_DIR/_sweep_common.sh"

if ! python3 scripts/noise_configs.py validate --list "$CONFIG_LIST" > /dev/null; then
    echo "FLEXFL_NOISE_LIST failed validation: $CONFIG_LIST" >&2
    exit 2
fi

REPO_RESULTS="$(realpath -m "$REPO_DIR/results")" || exit 2
case "$RESULTS_ROOT/" in
    "$REPO_RESULTS"/*)
        echo "FLEXFL_NOISE_ROOT must not be the campaign results tree or beneath it: $RESULTS_ROOT (results: $REPO_RESULTS)" >&2
        exit 2
        ;;
esac

marker_dir="$RESULTS_ROOT"
while :; do
    if [ -e "$marker_dir/.setup_complete" ]; then
        echo "Refusing FLEXFL_NOISE_ROOT $RESULTS_ROOT: $marker_dir/.setup_complete marks a campaign tree." >&2
        exit 2
    fi
    [ "$marker_dir" = "/" ] && break
    marker_dir="$(dirname "$marker_dir")"
done
if [ -d "$RESULTS_ROOT" ]; then
    marker_found="$(find "$RESULTS_ROOT" -name .setup_complete -print -quit)" || {
        echo "Cannot search FLEXFL_NOISE_ROOT $RESULTS_ROOT for .setup_complete." >&2
        exit 2
    }
    if [ -n "$marker_found" ]; then
        echo "Refusing FLEXFL_NOISE_ROOT $RESULTS_ROOT: $marker_found marks a campaign tree." >&2
        exit 2
    fi
fi

if [ ! -f "$IDS_FILE" ]; then
    echo "IDS file not found: $IDS_FILE (VMs must already be provisioned; this script never provisions them)." >&2
    exit 2
fi

mkdir -p "$RESULTS_ROOT"

execute_fl_run() {
    local ips_file="$1" data_name="$2" fl_algo="$3" seed="$4" hp_args="$5" total="$6"
    bash scripts/run_commands.sh -i "$ips_file" "rm -rf ~/flexfl/results"
    bash scripts/run_on_vms.sh -f "$ips_file" 0 0 \
        --dataset Benchmark --data_name "$data_name" --nn benchmark \
        --fl "$fl_algo" --seed "$seed" --min_workers "$total" \
        $hp_args "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
    run_rc=$?
}

noise_cfg() {
    python3 scripts/noise_configs.py "$@"
}

cleanup_dataset() {
    rm -rf "data/${data_name}"/node_*
    bash scripts/run_commands.sh -i "$IPS_SUBSET_TXT" "rm -rf ~/flexfl/data/${data_name}"
    bash scripts/run_commands.sh -i "$IPS_SUBSET_TXT" "rm -rf ~/flexfl/results"
}

out=$(noise_cfg groups --list "$CONFIG_LIST") || { echo "noise_configs.py failed" >&2; exit 2; }
if [ -z "$out" ]; then
    echo "noise_configs.py groups printed no groups for $CONFIG_LIST" >&2
    exit 2
fi
mapfile -t group_lines <<< "$out"

for group_line in "${group_lines[@]}"; do
    read -r strategy n1 n2 n3 <<< "$group_line"
    data_name=""; fl_algo=""
    total=$((n1 + n2 + n3))
    combo="atnog-test1_${n1}_hobbit_${n2}_samwise_${n3}"
    run_root="$RESULTS_ROOT/${strategy}/${combo}"
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

    out=$(noise_cfg datasets --list "$CONFIG_LIST" \
        --strategy "$strategy" --n1 "$n1" --n2 "$n2" --n3 "$n3") \
        || { echo "noise_configs.py failed" >&2; exit 2; }
    if [ -z "$out" ]; then
        echo "noise_configs.py datasets printed nothing for ${strategy}/${combo}" >&2
        exit 2
    fi
    mapfile -t dataset_lines <<< "$out"

    for data_name in "${dataset_lines[@]}"; do
        base="${run_root}/${data_name}"

        out=$(noise_cfg entries --list "$CONFIG_LIST" \
            --strategy "$strategy" --n1 "$n1" --n2 "$n2" --n3 "$n3" \
            --data-name "$data_name") \
            || { echo "noise_configs.py failed" >&2; exit 2; }
        if [ -z "$out" ]; then
            echo "noise_configs.py entries printed nothing for ${strategy}/${combo}/${data_name}" >&2
            exit 2
        fi
        mapfile -t entry_lines <<< "$out"

        all_done=1
        for entry_line in "${entry_lines[@]}"; do
            read -r fl_algo seed <<< "$entry_line"
            is_done "${base}/${fl_algo}/rep_1" || { all_done=0; break; }
        done
        fl_algo=""; seed=""
        if [ "$all_done" -eq 1 ]; then
            echo "  - ${combo}/${data_name}: all algos done, skipping"
            continue
        fi

        mkdir -p "$base"
        pflag=0
        [ -f "data/${data_name}/_data/x_train.npy" ] &&
            [ -f "data/${data_name}/_data/scaling.json" ] &&
            grep -q '"target"' "data/${data_name}/_data/scaling.json" ||
            pflag=1
        if ! bash scripts/dataset_division.sh -d "$data_name" -n "$total" -s "$strategy" -p "$pflag"; then
            log_failure "dataset_division"
            cleanup_dataset
            continue
        fi
        if ! bash scripts/send_dataset.sh -d "$data_name" -f "$IPS_SUBSET_TXT"; then
            log_failure "send_dataset"
            cleanup_dataset
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
  "split_version": 2,
  "preprocess": {"val_size": 0.2, "test_size": 0.2}
}
EOF
        uv run python scripts/compute_partition_entropy.py \
            --data-dir "data/${data_name}" --num-workers "$total" \
            --update-json "${base}/division.json" \
            || echo "  ! entropy computation failed for ${data_name} (continuing)" >&2

        read -r first_algo _ <<< "${entry_lines[0]}"
        expected_division="${base}/.expected_division.json"
        if ! noise_cfg field --list "$CONFIG_LIST" \
            --strategy "$strategy" --n1 "$n1" --n2 "$n2" --n3 "$n3" \
            --data-name "$data_name" --fl-algo "$first_algo" \
            --name expected_division --out "$expected_division"; then
            echo "noise_configs.py failed" >&2
            rm -f "$expected_division"
            cleanup_dataset
            exit 2
        fi
        if ! noise_cfg compare --expected "$expected_division" --actual "${base}/division.json" >&2; then
            log_failure "division_mismatch"
            rm -f "$expected_division"
            cleanup_dataset
            continue
        fi
        rm -f "$expected_division"

        for entry_line in "${entry_lines[@]}"; do
            read -r fl_algo seed <<< "$entry_line"
            run_dir="${base}/${fl_algo}/rep_1"
            if is_done "$run_dir"; then
                echo "    - ${fl_algo} rep 1: done, skipping"
                continue
            fi
            rm -rf "$run_dir"
            hp_file="${base}/.hp_${fl_algo}_${seed}.json"
            expected_hp="${base}/.expected_hp_${fl_algo}_${seed}.json"
            hp_args=$(sample_hp_args "$combo" "$data_name" "$fl_algo" "$seed" "$hp_file") \
                && [ -s "$hp_file" ] || {
                log_failure "sample_hyperparameters"
                rm -f "$hp_file"
                continue
            }
            if ! noise_cfg field --list "$CONFIG_LIST" \
                --strategy "$strategy" --n1 "$n1" --n2 "$n2" --n3 "$n3" \
                --data-name "$data_name" --fl-algo "$fl_algo" \
                --name expected_hyperparameters --out "$expected_hp"; then
                echo "noise_configs.py failed" >&2
                rm -f "$hp_file" "$expected_hp"
                cleanup_dataset
                exit 2
            fi
            if ! noise_cfg compare --expected "$expected_hp" --actual "$hp_file" >&2; then
                log_failure "hp_mismatch"
                rm -f "$hp_file" "$expected_hp"
                continue
            fi
            execute_fl_run "$IPS_SUBSET_TXT" "$data_name" "$fl_algo" "$seed" "$hp_args" "$total"

            bash scripts/gather_results.sh -f "$IPS_SUBSET_TXT" -o "$run_dir"

            if [ "$run_rc" -eq 0 ] && run_output_complete "$run_dir" "$total"; then
                cp -f "$hp_file" "$run_dir/hyperparameters.json"
                touch "$run_dir/_SUCCESS"
                if noise_cfg compare --expected "$expected_hp" --actual "$run_dir/hyperparameters.json" >&2; then
                    echo "    - ${fl_algo} rep 1: success"
                else
                    rm -f "$run_dir/_SUCCESS"
                    touch "$run_dir/_FAILED"
                    log_failure "hp_written_mismatch"
                    echo "    - ${fl_algo} rep 1: FAILED (written hyperparameters differ, marked _FAILED, will retry on re-run)"
                fi
            else
                touch "$run_dir/_FAILED"
                log_failure "run_on_vms"
                echo "    - ${fl_algo} rep 1: FAILED (marked _FAILED, will retry on re-run)"
            fi
            rm -f "$hp_file" "$expected_hp"
        done
        fl_algo=""; seed=""

        cleanup_dataset
    done
done

echo "=== Noise reruns complete. ==="
if [ -s "$FAIL_LOG" ]; then
    echo "Some steps failed and were skipped, see $FAIL_LOG ($(wc -l < "$FAIL_LOG") entries). Re-run this script to retry them; completed runs are skipped."
fi
