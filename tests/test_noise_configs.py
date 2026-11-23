import csv
import json
import re
import subprocess
import sys
from pathlib import Path

import noise_configs
import pytest
from sample_hyperparameters import sample as sample_hp

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "noise_configs.py"

STRATEGIES = ["iid", "non_iid", "dirichlet"]
ALGOS = [
    "CentralizedSync",
    "CentralizedAsync",
    "DecentralizedSync",
    "DecentralizedAsync",
]
DATASETS = [
    "clf_num_covertype",
    "clf_num_a",
    "clf_cat_b",
    "clf_num_c",
    "reg_num_d",
    "reg_cat_e",
    "reg_num_f",
    "reg_cat_g",
]
COMBOS = [(2, 2, 2), (2, 4, 8), (4, 8, 16), (8, 16, 16), (8, 16, 32)]
BAND_LABELS = ["6-16", "17-32", "33-44", "45-56"]
BAND_EDGES = [6, 17, 33, 45, 57]
CSV_COLUMNS = [
    "strategy",
    "combo",
    "n_atnog_test1",
    "n_hobbit",
    "n_samwise",
    "num_workers",
    "dataset",
    "fl_algo",
    "repeat",
    "performance",
    "total_time_s",
]


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
    )


def combo_name(n1, n2, n3):
    return f"atnog-test1_{n1}_hobbit_{n2}_samwise_{n3}"


def band_of(total):
    for label, lo, hi in zip(BAND_LABELS, BAND_EDGES, BAND_EDGES[1:]):
        if lo <= total < hi:
            return label
    return None


def make_entry(**over):
    entry = {
        "strategy": "iid",
        "n1": 2,
        "n2": 4,
        "n3": 8,
        "data_name": "clf_num_covertype",
        "fl_algo": "CentralizedSync",
        "seed": 42,
        "expected_hyperparameters": {"learning_rate": 0.0012, "batch_size": 256},
        "expected_division": {
            "split_version": 2,
            "worker_feature_entropy": {"mean": 0.5},
        },
    }
    entry.update(over)
    return entry


def write_list(path, entries):
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))


def synthetic_rows():
    rows = []
    for si, strategy in enumerate(STRATEGIES):
        for di, dataset in enumerate(DATASETS):
            for ai, algo in enumerate(ALGOS):
                for j in range(4):
                    ci = (si + di + ai + j) % len(COMBOS)
                    n1, n2, n3 = COMBOS[ci]
                    time_s = (10.0 * (ci + 1) + di) * (100 if di == 0 else 1)
                    rows.append(
                        {
                            "strategy": strategy,
                            "combo": combo_name(n1, n2, n3),
                            "n_atnog_test1": n1,
                            "n_hobbit": n2,
                            "n_samwise": n3,
                            "num_workers": n1 + n2 + n3,
                            "dataset": dataset,
                            "fl_algo": algo,
                            "repeat": 1,
                            "performance": 0.5,
                            "total_time_s": time_s,
                        }
                    )
                rows.append(
                    {
                        "strategy": strategy,
                        "combo": combo_name(3, 3, 3),
                        "n_atnog_test1": 3,
                        "n_hobbit": 3,
                        "n_samwise": 3,
                        "num_workers": 9,
                        "dataset": dataset,
                        "fl_algo": algo,
                        "repeat": 2,
                        "performance": 0.5,
                        "total_time_s": 1.0,
                    }
                )
    return rows


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def identity(entry):
    return (
        entry["strategy"],
        combo_name(entry["n1"], entry["n2"], entry["n3"]),
        entry["data_name"],
        entry["fl_algo"],
    )


def read_entries(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


@pytest.fixture
def csv_path(tmp_path):
    path = tmp_path / "inputs" / "in.csv"
    write_csv(path, synthetic_rows())
    return path


def sample_cmd(csv_file, out, *extra):
    return run("sample", "--csv", csv_file, "--out", out, *extra)


class TestValidate:
    def test_accepts_well_formed_two_line_list(self, tmp_path):
        lst = tmp_path / "l.jsonl"
        write_list(
            lst,
            [make_entry(), make_entry(fl_algo="CentralizedAsync")],
        )
        res = run("validate", "--list", lst)
        assert res.returncode == 0, res.stderr

    @pytest.mark.parametrize(
        "field",
        [
            "strategy",
            "n1",
            "n2",
            "n3",
            "data_name",
            "fl_algo",
            "seed",
            "expected_hyperparameters",
            "expected_division",
        ],
    )
    def test_rejects_missing_field(self, tmp_path, field):
        entry = make_entry()
        del entry[field]
        lst = tmp_path / "l.jsonl"
        write_list(lst, [make_entry(), entry])
        res = run("validate", "--list", lst)
        assert res.returncode == 1
        assert field in res.stderr
        assert "line 2" in res.stderr

    @pytest.mark.parametrize(
        "entries",
        [
            [make_entry(), make_entry()],
            [make_entry(seed=43)],
            [make_entry(strategy="random")],
            [make_entry(n1=0)],
            [make_entry(n2=-3)],
            [make_entry(n3=0)],
            [make_entry(data_name="../venv")],
            [make_entry(data_name="a/b")],
            [make_entry(data_name="")],
            [make_entry(data_name="-x")],
            [make_entry(data_name="a b")],
            [make_entry(fl_algo="Unknown")],
            [],
        ],
        ids=[
            "duplicate",
            "seed",
            "strategy",
            "n1-zero",
            "n2-negative",
            "n3-zero",
            "data-parent",
            "data-slash",
            "data-empty",
            "data-leading-dash",
            "data-space",
            "unknown-algorithm",
            "empty",
        ],
    )
    def test_rejects_bad_case(self, tmp_path, entries):
        lst = tmp_path / "l.jsonl"
        write_list(lst, entries)
        res = run("validate", "--list", lst)
        assert res.returncode == 1
        assert res.stderr.strip() != ""

    def test_rejects_invalid_json_line(self, tmp_path):
        lst = tmp_path / "l.jsonl"
        lst.write_text(json.dumps(make_entry()) + "\n{not json\n")
        res = run("validate", "--list", lst)
        assert res.returncode == 1
        assert "line 2" in res.stderr

    def test_allow_missing_expected_relaxes_only_expected_fields(self, tmp_path):
        bare = make_entry()
        del bare["expected_hyperparameters"]
        del bare["expected_division"]
        lst = tmp_path / "l.jsonl"
        write_list(lst, [bare])
        assert run("validate", "--list", lst).returncode == 1
        assert (
            run("validate", "--list", lst, "--allow-missing-expected").returncode == 0
        )

        no_seed = dict(bare)
        del no_seed["seed"]
        write_list(lst, [no_seed])
        res = run("validate", "--list", lst, "--allow-missing-expected")
        assert res.returncode == 1
        assert "seed" in res.stderr


class TestListCommands:
    def entries(self):
        return [
            make_entry(strategy="non_iid"),
            make_entry(strategy="iid"),
            make_entry(strategy="iid", n1=4, n2=2, n3=2),
            make_entry(strategy="iid", n1=2, n2=10, n3=8),
            make_entry(strategy="iid", data_name="reg_num_d"),
            make_entry(strategy="iid", fl_algo="DecentralizedAsync"),
        ]

    def test_groups_distinct_and_sorted(self, tmp_path):
        lst = tmp_path / "l.jsonl"
        write_list(lst, self.entries())
        res = run("groups", "--list", lst)
        assert res.returncode == 0, res.stderr
        assert res.stdout.splitlines() == [
            "iid 2 4 8",
            "iid 2 10 8",
            "iid 4 2 2",
            "non_iid 2 4 8",
        ]

    def test_datasets_and_entries(self, tmp_path):
        lst = tmp_path / "l.jsonl"
        write_list(lst, self.entries())
        res = run(
            "datasets",
            "--list",
            lst,
            "--strategy",
            "iid",
            "--n1",
            2,
            "--n2",
            4,
            "--n3",
            8,
        )
        assert res.returncode == 0, res.stderr
        assert res.stdout.splitlines() == ["clf_num_covertype", "reg_num_d"]
        res = run(
            "entries",
            "--list",
            lst,
            "--strategy",
            "iid",
            "--n1",
            2,
            "--n2",
            4,
            "--n3",
            8,
            "--data-name",
            "clf_num_covertype",
        )
        assert res.returncode == 0, res.stderr
        assert res.stdout.splitlines() == [
            "CentralizedSync 42",
            "DecentralizedAsync 42",
        ]

    def test_field_writes_the_named_object(self, tmp_path):
        lst = tmp_path / "l.jsonl"
        write_list(lst, self.entries())
        out = tmp_path / "hp.json"
        args = [
            "field",
            "--list",
            lst,
            "--strategy",
            "iid",
            "--n1",
            2,
            "--n2",
            4,
            "--n3",
            8,
            "--data-name",
            "clf_num_covertype",
            "--fl-algo",
            "CentralizedSync",
            "--out",
            out,
        ]
        res = run(*args, "--name", "expected_hyperparameters")
        assert res.returncode == 0, res.stderr
        assert json.loads(out.read_text()) == {
            "learning_rate": 0.0012,
            "batch_size": 256,
        }
        res = run(*args, "--name", "expected_division")
        assert res.returncode == 0, res.stderr
        assert json.loads(out.read_text()) == {
            "split_version": 2,
            "worker_feature_entropy": {"mean": 0.5},
        }

    def test_field_unknown_entry_exits_1(self, tmp_path):
        lst = tmp_path / "l.jsonl"
        write_list(lst, self.entries())
        res = run(
            "field",
            "--list",
            lst,
            "--strategy",
            "dirichlet",
            "--n1",
            2,
            "--n2",
            4,
            "--n3",
            8,
            "--data-name",
            "clf_num_covertype",
            "--fl-algo",
            "CentralizedSync",
            "--name",
            "expected_division",
            "--out",
            tmp_path / "x.json",
        )
        assert res.returncode == 1
        assert res.stderr.strip() != ""
        assert not (tmp_path / "x.json").exists()

    def test_compare_prints_one_line_per_difference(self, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        a.write_text(json.dumps({"lr": 0.1, "bs": 256}))
        b.write_text(json.dumps({"lr": 0.1 + 1e-12, "bs": 256}))
        assert run("compare", "--expected", a, "--actual", b).returncode == 0
        b.write_text(json.dumps({"lr": 0.2, "extra": 1}))
        res = run("compare", "--expected", a, "--actual", b)
        assert res.returncode == 1
        lines = [x for x in res.stdout.splitlines() if x.strip()]
        assert len(lines) == 3
        assert any("lr" in x for x in lines)
        assert any("bs" in x for x in lines)
        assert any("extra" in x for x in lines)


class TestDiffJson:
    def test_changed_float(self):
        diffs = noise_configs.diff_json({"lr": 0.1}, {"lr": 0.2})
        assert len(diffs) == 1
        assert "lr" in diffs[0]

    def test_missing_key(self):
        diffs = noise_configs.diff_json({"a": 1, "b": 2}, {"a": 1})
        assert len(diffs) == 1
        assert "b" in diffs[0]

    def test_extra_key(self):
        diffs = noise_configs.diff_json({"a": 1}, {"a": 1, "c": 3})
        assert len(diffs) == 1
        assert "c" in diffs[0]

    def test_tiny_relative_float_change_is_equal(self):
        assert (
            noise_configs.diff_json({"lr": 0.0012}, {"lr": 0.0012 * (1 + 1e-12)}) == []
        )

    def test_lists_elementwise(self):
        assert noise_configs.diff_json({"v": [1, 2, 3]}, {"v": [1, 2, 3]}) == []
        diffs = noise_configs.diff_json({"v": [1, 2, 3]}, {"v": [1, 5, 3]})
        assert len(diffs) == 1
        assert "v" in diffs[0]
        assert noise_configs.diff_json({"v": [1, 2]}, {"v": [1, 2, 3]}) != []

    def test_nested_and_type_change(self):
        assert noise_configs.diff_json({"a": {"b": "x"}}, {"a": {"b": "x"}}) == []
        assert len(noise_configs.diff_json({"a": {"b": "x"}}, {"a": {"b": "y"}})) == 1
        assert len(noise_configs.diff_json({"a": 1}, {"a": "1"})) == 1


class TestSeedGuard:
    def test_repeat1_seed_matches_launcher(self):
        text = (REPO / "scripts" / "run_full_experiments.sh").read_text()
        first = int(re.search(r"SEEDS=\((\d+)", text).group(1))
        assert noise_configs.REPEAT1_SEED == first

    def test_fl_algos_match_launcher(self):
        text = (REPO / "scripts" / "run_full_experiments.sh").read_text()
        line = next(line for line in text.splitlines() if line.startswith("fl_algos=("))
        assert noise_configs.FL_ALGOS == tuple(re.findall(r"\w+", line)[1:])

    def test_launcher_constants_match_replay_script(self):
        text = (REPO / "scripts" / "run_noise_reruns.sh").read_text()
        assert f"--dataset {noise_configs.LAUNCHER_DATASET} " in text
        assert f"--nn {noise_configs.LAUNCHER_NN} " in text

    def test_helpers(self):
        entry = make_entry()
        assert noise_configs.combo_of(entry) == "atnog-test1_2_hobbit_4_samwise_8"
        assert (
            noise_configs.key_of(entry)
            == "atnog-test1_2_hobbit_4_samwise_8|clf_num_covertype|CentralizedSync|42"
        )
        assert noise_configs.LIST_FIELDS == (
            "strategy",
            "n1",
            "n2",
            "n3",
            "data_name",
            "fl_algo",
            "seed",
            "expected_hyperparameters",
            "expected_division",
        )

    def test_read_list_names_line_and_field(self, tmp_path):
        lst = tmp_path / "l.jsonl"
        bad = make_entry()
        del bad["fl_algo"]
        write_list(lst, [make_entry(), bad])
        with pytest.raises(ValueError, match=r"line 2.*fl_algo"):
            noise_configs.read_list(lst)


class TestSample:
    def test_exactly_150_unique_entries_and_marginals_covered(self, csv_path, tmp_path):
        out = tmp_path / "list.jsonl"
        res = sample_cmd(csv_path, out, "--target", 150)
        assert res.returncode == 0, res.stderr
        entries = read_entries(out)
        assert len(entries) == 150
        assert len({identity(e) for e in entries}) == 150
        assert {e["strategy"] for e in entries} == set(STRATEGIES)
        assert {e["fl_algo"] for e in entries} == set(ALGOS)
        assert {e["data_name"] for e in entries} == set(DATASETS)
        totals = [e["n1"] + e["n2"] + e["n3"] for e in entries]
        assert {band_of(t) for t in totals} == set(BAND_LABELS)
        assert min(totals) == 6
        assert max(totals) == 56
        assert all(e["seed"] == 42 for e in entries)
        assert all("expected_hyperparameters" not in e for e in entries)
        assert all(list(e) == list(noise_configs.LIST_FIELDS[:7]) for e in entries)

    def test_dataset_counts_are_balanced(self, csv_path, tmp_path):
        out = tmp_path / "list.jsonl"
        assert sample_cmd(csv_path, out, "--target", 150).returncode == 0
        entries = read_entries(out)
        counts = {d: 0 for d in DATASETS}
        for e in entries:
            counts[e["data_name"]] += 1
        mean = 150 / len(DATASETS)
        assert all(abs(c - mean) <= 1 for c in counts.values()), counts

    def test_never_picks_repeat_2_and_does_not_write_beside_input(
        self, csv_path, tmp_path
    ):
        out = tmp_path / "list.jsonl"
        assert sample_cmd(csv_path, out, "--target", 150).returncode == 0
        entries = read_entries(out)
        assert all((e["n1"], e["n2"], e["n3"]) != (3, 3, 3) for e in entries)
        assert [p.name for p in csv_path.parent.iterdir()] == ["in.csv"]

    def test_deterministic_per_seed(self, csv_path, tmp_path):
        a = tmp_path / "a.jsonl"
        b = tmp_path / "b.jsonl"
        c = tmp_path / "c.jsonl"
        assert sample_cmd(csv_path, a, "--target", 150).returncode == 0
        assert sample_cmd(csv_path, b, "--target", 150).returncode == 0
        assert sample_cmd(csv_path, c, "--target", 150, "--seed", 75).returncode == 0
        assert a.read_bytes() == b.read_bytes()
        assert a.read_bytes() != c.read_bytes()

    def test_dataset_without_repeat_1_rows_exits_1(self, csv_path, tmp_path):
        rows = synthetic_rows()
        for row in rows:
            if row["dataset"] == DATASETS[7]:
                row["repeat"] = 2
        write_csv(csv_path, rows)
        out = tmp_path / "list.jsonl"
        res = sample_cmd(csv_path, out, "--target", 150)
        assert res.returncode == 1
        assert DATASETS[7] in res.stderr
        assert not out.exists()

    def test_csv_without_one_algorithm_exits_1(self, csv_path, tmp_path):
        rows = [row for row in synthetic_rows() if row["fl_algo"] != ALGOS[3]]
        write_csv(csv_path, rows)
        out = tmp_path / "list.jsonl"
        res = sample_cmd(csv_path, out, "--target", 150)
        assert res.returncode == 1
        assert ALGOS[3] in res.stderr
        assert not out.exists()

    def test_datasets_option_restricts_the_sample(self, csv_path, tmp_path):
        out = tmp_path / "list.jsonl"
        keep = DATASETS[:4]
        res = sample_cmd(csv_path, out, "--target", 40, "--datasets", ",".join(keep))
        assert res.returncode == 0, res.stderr
        assert {e["data_name"] for e in read_entries(out)} == set(keep)

    def test_listed_dataset_absent_from_csv_exits_1(self, csv_path, tmp_path):
        out = tmp_path / "list.jsonl"
        listed = ",".join(DATASETS[:4] + ["clf_num_missing"])
        res = sample_cmd(csv_path, out, "--target", 40, "--datasets", listed)
        assert res.returncode == 1
        assert "clf_num_missing" in res.stderr
        assert not out.exists()

    def test_band_without_candidates_exits_1(self, csv_path, tmp_path):
        rows = [r for r in synthetic_rows() if r["num_workers"] < 45]
        write_csv(csv_path, rows)
        out = tmp_path / "list.jsonl"
        res = sample_cmd(csv_path, out, "--target", 150)
        assert res.returncode == 1
        assert "45-56" in res.stderr
        assert not out.exists()

    def test_target_below_marginal_coverage_exits_1(self, csv_path, tmp_path):
        out = tmp_path / "list.jsonl"
        res = sample_cmd(csv_path, out, "--target", 3)
        assert res.returncode == 1
        assert "target" in res.stderr
        assert not out.exists()

    def test_duplicate_identity_exits_1(self, csv_path, tmp_path):
        rows = synthetic_rows()
        rows.append(dict(rows[0]))
        write_csv(csv_path, rows)
        out = tmp_path / "list.jsonl"
        res = sample_cmd(csv_path, out, "--target", 150)
        assert res.returncode == 1
        assert not out.exists()

    def test_list_without_expected_needs_the_flag(self, csv_path, tmp_path):
        out = tmp_path / "list.jsonl"
        assert sample_cmd(csv_path, out, "--target", 150).returncode == 0
        assert run("validate", "--list", out).returncode == 1
        res = run("validate", "--list", out, "--allow-missing-expected")
        assert res.returncode == 0, res.stderr

    def test_summary(self, csv_path, tmp_path):
        out = tmp_path / "list.jsonl"
        summary = tmp_path / "summary.json"
        res = sample_cmd(csv_path, out, "--target", 150, "--summary-out", summary)
        assert res.returncode == 0, res.stderr
        entries = read_entries(out)
        data = json.loads(summary.read_text())
        times = {
            (r["strategy"], r["combo"], r["dataset"], r["fl_algo"]): float(
                r["total_time_s"]
            )
            for r in synthetic_rows()
            if r["repeat"] == 1
        }
        groups = {(e["strategy"], e["n1"], e["n2"], e["n3"]) for e in entries}
        triples = {
            (e["strategy"], e["n1"], e["n2"], e["n3"], e["data_name"]) for e in entries
        }
        assert data["n_groups"] == len(groups)
        assert data["n_group_dataset_pairs"] == len(triples)
        expected_total = sum(times[identity(e)] for e in entries)
        assert data["estimated_run_seconds"] == pytest.approx(expected_total)
        covertype_total = sum(
            times[identity(e)] for e in entries if e["data_name"] == DATASETS[0]
        )
        assert data["estimated_run_seconds_by_dataset"][DATASETS[0]] == pytest.approx(
            covertype_total
        )
        for key, field in (
            ("by_strategy", "strategy"),
            ("by_fl_algo", "fl_algo"),
            ("by_dataset", "data_name"),
        ):
            for value, count in data[key].items():
                assert count == sum(1 for e in entries if e[field] == value)
            assert sum(data[key].values()) == 150
        for label in BAND_LABELS:
            assert data["by_band"][label] == sum(
                1 for e in entries if band_of(e["n1"] + e["n2"] + e["n3"]) == label
            )
        assert data["min_worker_total"] == 6
        assert data["max_worker_total"] == 56


@pytest.fixture
def results_tree(tmp_path):
    root = tmp_path / "results"
    for row in synthetic_rows():
        if row["repeat"] != 1:
            continue
        base = root / row["strategy"] / row["combo"] / row["dataset"]
        key = f"{row['combo']}|{row['dataset']}|{row['fl_algo']}|42"
        hp_dir = base / row["fl_algo"] / "rep_1"
        hp_dir.mkdir(parents=True, exist_ok=True)
        vector = sample_hp(row["fl_algo"], key)
        (hp_dir / "hyperparameters.json").write_text(json.dumps(vector))
        (hp_dir / "master").mkdir(exist_ok=True)
        (hp_dir / "master" / "log_0.jsonl").write_text("{}\n")
        (hp_dir / "master" / "args.json").write_text(
            json.dumps(
                {
                    "dataset": noise_configs.LAUNCHER_DATASET,
                    "data_name": row["dataset"],
                    "nn": noise_configs.LAUNCHER_NN,
                    "fl": row["fl_algo"],
                    "seed": 42,
                    "min_workers": row["num_workers"],
                    **vector,
                }
            )
        )
        (base / "division.json").write_text(
            json.dumps(
                {
                    "split_version": 2,
                    "strategy": row["strategy"],
                    "worker_feature_entropy": {"mean": 0.25},
                }
            )
        )
    return root


class TestSampleResultsDir:
    def test_embeds_verified_files(self, csv_path, results_tree, tmp_path):
        out = tmp_path / "list.jsonl"
        res = sample_cmd(csv_path, out, "--target", 20, "--results-dir", results_tree)
        assert res.returncode == 0, res.stderr
        entries = read_entries(out)
        assert len(entries) == 20
        for e in entries:
            combo = combo_name(e["n1"], e["n2"], e["n3"])
            base = results_tree / e["strategy"] / combo / e["data_name"]
            hp = json.loads(
                (base / e["fl_algo"] / "rep_1" / "hyperparameters.json").read_text()
            )
            assert e["expected_hyperparameters"] == hp
            assert e["expected_division"] == json.loads(
                (base / "division.json").read_text()
            )
            assert list(e) == list(noise_configs.LIST_FIELDS)
        assert run("validate", "--list", out).returncode == 0

    def test_tampered_hyperparameters_exit_1_and_write_no_list(
        self, csv_path, results_tree, tmp_path
    ):
        first = tmp_path / "first.jsonl"
        assert (
            sample_cmd(
                csv_path, first, "--target", 20, "--results-dir", results_tree
            ).returncode
            == 0
        )
        victim = read_entries(first)[0]
        strategy, combo, dataset, algo = identity(victim)
        hp_file = (
            results_tree
            / strategy
            / combo
            / dataset
            / algo
            / "rep_1"
            / "hyperparameters.json"
        )
        stored = json.loads(hp_file.read_text())
        stored["learning_rate"] = 0.5
        hp_file.write_text(json.dumps(stored))

        out = tmp_path / "second.jsonl"
        summary = tmp_path / "summary.json"
        res = sample_cmd(
            csv_path,
            out,
            "--target",
            20,
            "--results-dir",
            results_tree,
            "--summary-out",
            summary,
        )
        assert res.returncode == 1
        assert f"{strategy}/{combo}/{dataset}/{algo}" in res.stderr
        assert "learning_rate" in res.stderr
        assert not out.exists()
        assert not summary.exists()

    def test_null_artifacts_exit_1_and_write_no_list(
        self, csv_path, results_tree, tmp_path
    ):
        first = tmp_path / "first.jsonl"
        assert (
            sample_cmd(
                csv_path, first, "--target", 20, "--results-dir", results_tree
            ).returncode
            == 0
        )
        selected = read_entries(first)
        hp_entry = selected[0]
        division_entry = next(
            entry for entry in selected if entry["data_name"] != hp_entry["data_name"]
        )
        hp_id = identity(hp_entry)
        division_id = identity(division_entry)
        hp_base = results_tree / hp_id[0] / hp_id[1] / hp_id[2]
        division_base = results_tree / division_id[0] / division_id[1] / division_id[2]
        (hp_base / hp_id[3] / "rep_1" / "hyperparameters.json").write_text("null")
        (division_base / "division.json").write_text("null")

        out = tmp_path / "second.jsonl"
        res = sample_cmd(csv_path, out, "--target", 20, "--results-dir", results_tree)
        assert res.returncode == 1
        assert "/".join(hp_id) in res.stderr
        assert "/".join(division_id) in res.stderr
        assert not out.exists()

    @pytest.mark.parametrize(
        "key, value", [("seed", 43), ("learning_rate", 0.5), ("min_workers", 2)]
    )
    def test_original_args_override_exits_1_and_writes_no_list(
        self, csv_path, results_tree, tmp_path, key, value
    ):
        first = tmp_path / "first.jsonl"
        assert (
            sample_cmd(
                csv_path, first, "--target", 20, "--results-dir", results_tree
            ).returncode
            == 0
        )
        victim = identity(read_entries(first)[0])
        args_file = (
            results_tree.joinpath(*victim[:3], victim[3], "rep_1")
            / "master"
            / "args.json"
        )
        stored = json.loads(args_file.read_text())
        stored[key] = value
        args_file.write_text(json.dumps(stored))

        out = tmp_path / "second.jsonl"
        res = sample_cmd(csv_path, out, "--target", 20, "--results-dir", results_tree)
        assert res.returncode == 1
        assert "/".join(victim) in res.stderr
        assert key in res.stderr
        assert not out.exists()

    def test_missing_original_args_json_exits_1(self, csv_path, results_tree, tmp_path):
        first = tmp_path / "first.jsonl"
        assert (
            sample_cmd(
                csv_path, first, "--target", 20, "--results-dir", results_tree
            ).returncode
            == 0
        )
        victim = identity(read_entries(first)[0])
        (
            results_tree.joinpath(*victim[:3], victim[3], "rep_1")
            / "master"
            / "args.json"
        ).unlink()

        out = tmp_path / "second.jsonl"
        res = sample_cmd(csv_path, out, "--target", 20, "--results-dir", results_tree)
        assert res.returncode == 1
        assert "/".join(victim) in res.stderr
        assert "args.json" in res.stderr
        assert not out.exists()

    def test_missing_division_lists_identity(self, csv_path, results_tree, tmp_path):
        first = tmp_path / "first.jsonl"
        assert (
            sample_cmd(
                csv_path, first, "--target", 20, "--results-dir", results_tree
            ).returncode
            == 0
        )
        victim = read_entries(first)[0]
        strategy, combo, dataset, algo = identity(victim)
        (results_tree / strategy / combo / dataset / "division.json").unlink()
        out = tmp_path / "second.jsonl"
        res = sample_cmd(csv_path, out, "--target", 20, "--results-dir", results_tree)
        assert res.returncode == 1
        assert f"{strategy}/{combo}/{dataset}/{algo}" in res.stderr
        assert not out.exists()

    def test_division_without_entropy_is_rejected(
        self, csv_path, results_tree, tmp_path
    ):
        first = tmp_path / "first.jsonl"
        assert (
            sample_cmd(
                csv_path, first, "--target", 20, "--results-dir", results_tree
            ).returncode
            == 0
        )
        victim = read_entries(first)[0]
        strategy, combo, dataset, algo = identity(victim)
        div = results_tree / strategy / combo / dataset / "division.json"
        div.write_text(json.dumps({"split_version": 2}))
        out = tmp_path / "second.jsonl"
        res = sample_cmd(csv_path, out, "--target", 20, "--results-dir", results_tree)
        assert res.returncode == 1
        assert "worker_feature_entropy" in res.stderr
        assert not out.exists()


class TestArgsCheck:
    ALGO = "CentralizedSync"
    DATA = "clf_num_a"
    KEY = f"atnog-test1_2_hobbit_2_samwise_2|{DATA}|{ALGO}|42"

    def _check(self, tmp_path, **overrides):
        vector = sample_hp(self.ALGO, self.KEY)
        args = {
            "dataset": noise_configs.LAUNCHER_DATASET,
            "data_name": self.DATA,
            "nn": noise_configs.LAUNCHER_NN,
            "fl": self.ALGO,
            "seed": 42,
            "min_workers": 6,
            **vector,
        }
        args.update(overrides)
        args = {k: v for k, v in args.items() if v is not None}
        (tmp_path / "args.json").write_text(json.dumps(args))
        (tmp_path / "hp.json").write_text(json.dumps(vector))
        return run(
            "args-check",
            "--args-json",
            tmp_path / "args.json",
            "--expected-hp",
            tmp_path / "hp.json",
            "--seed",
            42,
            "--data-name",
            self.DATA,
            "--fl-algo",
            self.ALGO,
            "--min-workers",
            6,
        )

    def test_matching_arguments_pass(self, tmp_path):
        res = self._check(tmp_path)
        assert res.returncode == 0, res.stdout + res.stderr

    @pytest.mark.parametrize(
        "key, value",
        [
            ("seed", 43),
            ("min_workers", 2),
            ("dataset", "Other"),
            ("nn", "other"),
            ("data_name", "clf_num_b"),
            ("fl", "CentralizedAsync"),
            ("learning_rate", 0.5),
            ("epochs", None),
        ],
    )
    def test_each_differing_or_missing_argument_fails(self, tmp_path, key, value):
        res = self._check(tmp_path, **{key: value})
        assert res.returncode == 1
        assert key in res.stdout
