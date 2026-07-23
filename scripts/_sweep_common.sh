#!/bin/bash

# Shared orchestration helpers + sweep-loop skeleton for run_test_experiment.sh and
# run_full_experiments.sh. Sourced, not executed directly.
#
# Expects these globals set by the sourcing script before run_sweep is called:
#   distributions, atnog_test1, hobbit, samwise, datasets, fl_algos   (arrays)
#   REPEATS, SEEDS                                                    (bound-checked via check_seeds_or_exit)
#   IDS_FILE, IDS_SUBSET, IPS_SUBSET, IPS_SUBSET_TXT, RESULTS_ROOT, PXM_DIR, FAIL_LOG
#   EXTRA_ARGS                                                        (array)
# and a caller-defined execute_fl_run function (invoked as
# `execute_fl_run "$ips_file" "$data_name" "$fl_algo" "$seed" "$hp_args"`) that must
# set the global $run_rc to the run's exit code.

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

check_seeds_or_exit() {
    if [ "$REPEATS" -gt "${#SEEDS[@]}" ]; then
        echo "FLEXFL_REPEATS=$REPEATS exceeds the ${#SEEDS[@]} predefined seeds in SEEDS — add more." >&2
        exit 1
    fi
}

# --- Sweep (fault-tolerant, resumable) ---
run_sweep() {
    for strategy in "${distributions[@]}"; do
        for n1 in "${atnog_test1[@]}"; do
            for n2 in "${hobbit[@]}"; do
                for n3 in "${samwise[@]}"; do
                    total=$((n1 + n2 + n3))
                    combo="atnog-test1_${n1}_hobbit_${n2}_samwise_${n3}"
                    # Strategy MUST be in the path: the same node-combo is swept under all
                    # three distributions, so without this segment their result dirs collide
                    # and resume would skip non_iid/dirichlet after iid completes.
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
                                execute_fl_run "$IPS_SUBSET_TXT" "$data_name" "$fl_algo" "$seed" "$hp_args"

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
}
