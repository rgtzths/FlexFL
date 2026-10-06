# Dataset preprocessing audit

Features are standardized with training-split statistics (T068) and regression targets likewise (T069).

Keep standard scaling for every dataset. Rows whose features are all -999 are dropped at preprocessing. No HPO re-tune.

Worker-feature entropy before and after T068 is not comparable, so the meta-dataset is built only from runs gathered after the T068 relaunch on 2026-10-05, and older corpora stay archived outside `results/`.

No HPO re-tune: at learning rate 1e-3 the tuned network beats the constant baseline on every sanity dataset except reg_cat_delays_zurich_transport. The boosting reference does not beat the constant baseline on reg_cat_delays_zurich_transport, reg_num_delays_zurich_transport either, so the metric carries little signal there.

Network scores are the best validation score over at most 40 epochs (patience 8), so they are optimistic against the boosting reference, which has no selection.

The static audit describes raw rows before the all -999 drop, so its row counts include the all -999 rows, counted over train, val and test, for: clf_num_MiniBooNE (173).

The sweep reuses any `data/<name>/_data` cache that holds `scaling.json`. Before the tier-20 pass, delete `data/<name>/_data` for clf_num_MiniBooNE on any host where that cache holds `scaling.json` and was built before the drop, so preprocessing runs again.

Run the scripts from the repository root. The all -999 drop applies to the Benchmark datasets only. The HPO configs come from results/hyperparameter_optimization, which is not tracked. A first-time preprocess needs network access to the Hugging Face Hub or revision 8d0ff9103525b7e3579b180230fddb3186258301 in the local Hugging Face cache.

## Audit provenance

```json
{
  "git_commit": "4092ac2490ee8f8d90642b78c95f916a0ffdddda",
  "git_dirty": false,
  "sources_sha256": {
    "scripts/audit_common.py": "0e8a2d961ff4ba014fc74545d13cdcaf994ef6b4d6a8ca6a807ebc0c6a6a2986",
    "scripts/audit_datasets.py": "dacc37a9627ca5f0cb1533d40156fb351b27ae24eac03ba23cee71c097e1a29e",
    "scripts/audit_central_sanity.py": "4674eabbe35228e7c29e51442891ea3537ed5f05e710af6ba53fb0ea3a800499",
    "scripts/render_dataset_audit.py": "dd55e16f9d626542776fe95ac6fe8755144c41d2ac52129ac07477baf577b18d",
    "src/flexfl/datasets/Benchmark.py": "50b72c382fa48e16747a78b52e550c0473036d69abef221ff3a947506d09e693",
    "src/flexfl/builtins/DatasetABC.py": "bcb5146fb430f3dd1fa252ef101b85678548ef98373f678e7cfeb4d0e570b2b9"
  },
  "hf_dataset": "inria-soda/tabular-benchmark",
  "hf_revision": "8d0ff9103525b7e3579b180230fddb3186258301",
  "val_size": 0.2,
  "test_size": 0.2,
  "versions": {
    "numpy": "2.0.2",
    "scipy": "1.15.2",
    "scikit-learn": "1.6.1",
    "datasets": "4.2.0"
  }
}
```

## Central sanity provenance

```json
{
  "after": {
    "git_commit": "4092ac2490ee8f8d90642b78c95f916a0ffdddda",
    "git_dirty": false,
    "sources_sha256": {
      "scripts/audit_common.py": "0e8a2d961ff4ba014fc74545d13cdcaf994ef6b4d6a8ca6a807ebc0c6a6a2986",
      "scripts/audit_datasets.py": "dacc37a9627ca5f0cb1533d40156fb351b27ae24eac03ba23cee71c097e1a29e",
      "scripts/audit_central_sanity.py": "4674eabbe35228e7c29e51442891ea3537ed5f05e710af6ba53fb0ea3a800499",
      "scripts/render_dataset_audit.py": "dd55e16f9d626542776fe95ac6fe8755144c41d2ac52129ac07477baf577b18d",
      "src/flexfl/datasets/Benchmark.py": "50b72c382fa48e16747a78b52e550c0473036d69abef221ff3a947506d09e693",
      "src/flexfl/builtins/DatasetABC.py": "bcb5146fb430f3dd1fa252ef101b85678548ef98373f678e7cfeb4d0e570b2b9"
    },
    "hf_dataset": "inria-soda/tabular-benchmark",
    "hf_revision": "8d0ff9103525b7e3579b180230fddb3186258301",
    "val_size": 0.2,
    "test_size": 0.2,
    "versions": {
      "numpy": "2.0.2",
      "scipy": "1.15.2",
      "scikit-learn": "1.6.1",
      "datasets": "4.2.0"
    },
    "run_constants": {
      "MAX_TRAIN": 100000,
      "EPOCHS": 40,
      "PATIENCE": 8,
      "BATCH": 512,
      "LRS": [
        0.001,
        0.0001
      ],
      "SEED": 42
    },
    "keep_sentinel_rows": false,
    "hpo_sha256": {
      "clf_num_Bioresponse": "065e91223b01e68c352d9044b855c823e3587c3364278b52681d63e18fa7f326",
      "reg_cat_delays_zurich_transport": "deb05aab993299165fa58e5b175735925368aa29eae8ab0f1bf7942082cec61b",
      "reg_num_abalone": "f439ca78f2c08b57161fb601d5aa7e7a448d8b7d5100f89ec7c0d3d813c0d08d",
      "clf_cat_electricity": "8f36a0f1f2b13a13c4b1d6e1d206bda5ae9a44e827ba49e5122cb5b110f7ac3b",
      "reg_cat_Mercedes_Benz_Greener_Manufacturing": "d19824606da76d7be9d5ffd1a176e3d4be1f5fb62781bcf760a35a09998b68dc",
      "clf_num_covertype": "f6a17c16643528c3a2f0446892468331c1c20c9e63b490df371ae7cd45483958",
      "reg_num_delays_zurich_transport": "a35cbc971102010a78120cd65870b2202aa1f0240305261534789cb2d04dd53f",
      "reg_cat_visualizing_soil": "035aeeb7e95348899d4bb3e6598ce554ebab37d298dbdd347ef0c9ed6b99f439",
      "clf_num_eye_movements": "5f033b34b8b5863d5085a3d5b8a76294dc58b9da32b8a406509a14305ebf2ae5",
      "reg_cat_Allstate_Claims_Severity": "030698aa2ffa83d08b0cfd0ee73305729ea35364a615e7a6d62ae346159f8f52",
      "reg_num_superconduct": "1f83de19558c096c0d89db931efb7f8f77837fcb1a7dcbea65f67fdd22aa3edf",
      "reg_num_medical_charges": "11a7d379da87db52ddc888c8816e879c4e38617456edf6f71bde37d6d583fff3",
      "clf_cat_covertype": "97879bb651ae1ad58093122cecb97e56d2bfe4a1e4710f41b0e61c91af7fc5f1",
      "reg_cat_SGEMM_GPU_kernel_performance": "5a59927c7c9fb3693fa5ddcfe760494c6fef73414360f4c63a130358544d46c3",
      "clf_num_MiniBooNE": "fdf98a4922affb79a9415ebf3508e030b1f7a9f32dd09358a06c132ff4682b08",
      "reg_cat_house_sales": "9a9b7a8552fd7d96f22fe2d39abc3947f978160cfe477589b3a206dcf2202233",
      "clf_cat_eye_movements": "a6ddd64801262e63f872c5a6488a7f4bf008df7b5db705e2e0971143fa31854f",
      "clf_num_electricity": "e7b11edde6181c20671d37f129212914bb9e753ad73e70d3d86d070b237b86a4",
      "reg_num_house_16H": "631bd503f6fde41880b8c0fcd13de0826e1449efca0b008429460be40468d96f",
      "reg_num_nyc-taxi-green-dec-2016": "e9c34cb4754ba0b8aca38b5778c16cd688c9af1f32073aea98bc08b1784e632c"
    }
  },
  "before": {
    "git_commit": "4092ac2490ee8f8d90642b78c95f916a0ffdddda",
    "git_dirty": false,
    "sources_sha256": {
      "scripts/audit_common.py": "0e8a2d961ff4ba014fc74545d13cdcaf994ef6b4d6a8ca6a807ebc0c6a6a2986",
      "scripts/audit_datasets.py": "dacc37a9627ca5f0cb1533d40156fb351b27ae24eac03ba23cee71c097e1a29e",
      "scripts/audit_central_sanity.py": "4674eabbe35228e7c29e51442891ea3537ed5f05e710af6ba53fb0ea3a800499",
      "scripts/render_dataset_audit.py": "dd55e16f9d626542776fe95ac6fe8755144c41d2ac52129ac07477baf577b18d",
      "src/flexfl/datasets/Benchmark.py": "50b72c382fa48e16747a78b52e550c0473036d69abef221ff3a947506d09e693",
      "src/flexfl/builtins/DatasetABC.py": "bcb5146fb430f3dd1fa252ef101b85678548ef98373f678e7cfeb4d0e570b2b9"
    },
    "hf_dataset": "inria-soda/tabular-benchmark",
    "hf_revision": "8d0ff9103525b7e3579b180230fddb3186258301",
    "val_size": 0.2,
    "test_size": 0.2,
    "versions": {
      "numpy": "2.0.2",
      "scipy": "1.15.2",
      "scikit-learn": "1.6.1",
      "datasets": "4.2.0"
    },
    "run_constants": {
      "MAX_TRAIN": 100000,
      "EPOCHS": 40,
      "PATIENCE": 8,
      "BATCH": 512,
      "LRS": [
        0.001,
        0.0001
      ],
      "SEED": 42
    },
    "keep_sentinel_rows": true,
    "hpo_sha256": {
      "clf_num_MiniBooNE": "fdf98a4922affb79a9415ebf3508e030b1f7a9f32dd09358a06c132ff4682b08"
    }
  }
}
```

## Static audit

| dataset | tier 20 | task | train rows | features | max abs z | features with abs z above 10 | all -999 rows | duplicate train rows | label conflicts | imbalance ratio / target skew | flags | action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| clf_cat_albert |  | clf | 34951 | 31 | 84.70 | 19 | 0 | 0.0% | 0.0% | 1.00 | extreme_outliers_z50,heavy_tails | standard scaling |
| clf_cat_compas-two-years |  | clf | 2979 | 11 | 25.18 | 1 | 0 | 47.5% | 45.5% | 1.00 | outliers_z10,many_duplicate_rows,duplicate_label_conflicts | standard scaling |
| clf_cat_covertype | yes | clf | 254208 | 54 | 98.87 | 21 | 0 | 0.0% | 0.0% | 1.00 | constant_features,extreme_outliers_z50,duplicate_columns | standard scaling |
| clf_cat_default-of-credit-card-clients |  | clf | 7963 | 21 | 77.61 | 6 | 0 | 0.2% | 0.1% | 1.00 | extreme_outliers_z50,heavy_tails | standard scaling |
| clf_cat_electricity | yes | clf | 23084 | 8 | 80.34 | 2 | 0 | 0.0% | 0.0% | 1.00 | extreme_outliers_z50,heavy_tails | standard scaling |
| clf_cat_eye_movements | yes | clf | 4564 | 23 | 18.50 | 10 | 0 | 0.0% | 0.0% | 1.00 | outliers_z10,heavy_tails | standard scaling |
| clf_cat_road-safety |  | clf | 67057 | 32 | 23.67 | 12 | 0 | 0.0% | 0.0% | 1.00 | outliers_z10,heavy_tails | standard scaling |
| clf_num_Bioresponse | yes | clf | 2060 | 419 | 87.68 | 286 | 0 | 0.0% | 0.0% | 1.00 | extreme_outliers_z50,heavy_tails | standard scaling |
| clf_num_Diabetes130US |  | clf | 42654 | 7 | 87.97 | 3 | 0 | 12.3% | 12.3% | 1.00 | extreme_outliers_z50,heavy_tails,many_duplicate_rows,duplicate_label_conflicts | standard scaling |
| clf_num_Higgs |  | clf | 564096 | 24 | 57.91 | 13 | 0 | 0.1% | 0.0% | 1.00 | extreme_outliers_z50,heavy_tails | standard scaling |
| clf_num_MagicTelescope |  | clf | 8025 | 10 | 11.02 | 1 | 0 | 0.5% | 0.0% | 1.00 | outliers_z10 | standard scaling |
| clf_num_MiniBooNE | yes | clf | 43798 | 50 | 209.28 | 48 | 173 | 0.2% | 0.2% | 1.00 | extreme_outliers_z50,heavy_tails,all_sentinel_rows | standard scaling; drop all -999 rows (173) |
| clf_num_bank-marketing |  | clf | 6346 | 7 | 25.10 | 4 | 0 | 0.0% | 0.0% | 1.00 | outliers_z10,heavy_tails | standard scaling |
| clf_num_california |  | clf | 12380 | 8 | 99.76 | 4 | 0 | 0.0% | 0.0% | 1.00 | extreme_outliers_z50,heavy_tails | standard scaling |
| clf_num_covertype | yes | clf | 339961 | 10 | 11.31 | 1 | 0 | 0.0% | 0.0% | 1.00 | outliers_z10 | standard scaling |
| clf_num_credit |  | clf | 10028 | 10 | 136.13 | 7 | 0 | 0.0% | 0.0% | 1.00 | extreme_outliers_z50,heavy_tails | standard scaling |
| clf_num_default-of-credit-card-clients |  | clf | 7963 | 20 | 77.61 | 6 | 0 | 0.4% | 0.2% | 1.00 | extreme_outliers_z50,heavy_tails | standard scaling |
| clf_num_electricity | yes | clf | 23084 | 7 | 80.34 | 2 | 0 | 0.0% | 0.0% | 1.00 | extreme_outliers_z50,heavy_tails | standard scaling |
| clf_num_eye_movements | yes | clf | 4564 | 20 | 18.50 | 10 | 0 | 0.0% | 0.0% | 1.00 | outliers_z10,heavy_tails | standard scaling |
| clf_num_heloc |  | clf | 6000 | 22 | 29.23 | 4 | 0 | 5.4% | 5.4% | 1.00 | outliers_z10,heavy_tails,many_duplicate_rows,duplicate_label_conflicts | standard scaling |
| clf_num_house_16H |  | clf | 8092 | 16 | 77.36 | 6 | 0 | 0.0% | 0.0% | 1.00 | extreme_outliers_z50,heavy_tails | standard scaling |
| clf_num_jannis |  | clf | 34548 | 54 | 43.87 | 14 | 0 | 0.0% | 0.0% | 1.00 | outliers_z10,heavy_tails | standard scaling |
| clf_num_pol |  | clf | 6049 | 26 | 22.44 | 16 | 0 | 0.2% | 0.0% | 1.00 | outliers_z10,heavy_tails | standard scaling |
| reg_cat_Airlines_DepDelay_1M |  | reg | 600000 | 5 | 7.68 | 0 | 0 | 0.1% | 0.0% | 0.52 |  | standard scaling |
| reg_cat_Allstate_Claims_Severity | yes | reg | 112990 | 124 | 79.22 | 37 | 0 | 0.0% | 0.0% | 0.10 | extreme_outliers_z50 | standard scaling |
| reg_cat_Bike_Sharing_Demand |  | reg | 10427 | 11 | 6.01 | 0 | 0 | 0.3% | 0.0% | 1.28 |  | standard scaling |
| reg_cat_Brazilian_houses |  | reg | 6415 | 11 | 79.18 | 5 | 0 | 3.1% | 0.0% | 0.30 | extreme_outliers_z50,heavy_tails | standard scaling |
| reg_cat_Mercedes_Benz_Greener_Manufacturing | yes | reg | 2525 | 359 | 50.24 | 122 | 0 | 16.9% | 0.0% | 1.21 | constant_features,extreme_outliers_z50,many_duplicate_rows,duplicate_columns,target_outliers | standard scaling |
| reg_cat_SGEMM_GPU_kernel_performance | yes | reg | 144960 | 9 | 8.65 | 0 | 0 | 0.1% | 0.0% | 0.79 |  | standard scaling |
| reg_cat_abalone |  | reg | 2506 | 8 | 22.83 | 1 | 0 | 0.0% | 0.0% | 1.11 | outliers_z10,heavy_tails | standard scaling |
| reg_cat_analcatdata_supreme |  | reg | 2431 | 7 | 18.47 | 1 | 0 | 80.7% | 0.0% | -2.35 | outliers_z10,many_duplicate_rows,skewed_target | standard scaling |
| reg_cat_delays_zurich_transport | yes | reg | 3279345 | 11 | 14.03 | 1 | 0 | 99.4% | 0.0% | -0.87 | outliers_z10,heavy_tails,many_duplicate_rows | standard scaling |
| reg_cat_diamonds |  | reg | 32364 | 9 | 46.22 | 4 | 0 | 0.4% | 0.0% | 0.12 | outliers_z10,heavy_tails | standard scaling |
| reg_cat_house_sales | yes | reg | 12967 | 17 | 41.33 | 6 | 0 | 0.0% | 0.0% | 0.43 | outliers_z10,heavy_tails | standard scaling |
| reg_cat_medical_charges |  | reg | 97839 | 3 | 64.83 | 3 | 0 | 0.0% | 0.0% | 0.88 | extreme_outliers_z50,heavy_tails | standard scaling |
| reg_cat_nyc-taxi-green-dec-2016 |  | reg | 349101 | 16 | 98.84 | 5 | 0 | 0.5% | 0.0% | -0.00 | extreme_outliers_z50,heavy_tails | standard scaling |
| reg_cat_particulate-matter-ukair-2017 |  | reg | 236579 | 6 | 49.56 | 1 | 0 | 0.8% | 0.0% | -0.54 | outliers_z10,heavy_tails | standard scaling |
| reg_cat_seattlecrime6 |  | reg | 31218 | 4 | 1.66 | 0 | 0 | 98.7% | 0.0% | -0.42 | many_duplicate_rows | standard scaling |
| reg_cat_topo_2_1 |  | reg | 5331 | 255 | 245.28 | 115 | 0 | 0.2% | 0.0% | -2.23 | constant_features,extreme_outliers_z50,heavy_tails,duplicate_columns,skewed_target,target_outliers | standard scaling |
| reg_cat_visualizing_soil | yes | reg | 5184 | 4 | 4.00 | 0 | 0 | 0.0% | 0.0% | 0.33 |  | standard scaling |
| reg_num_Ailerons |  | reg | 8250 | 33 | 16.62 | 4 | 0 | 0.0% | 0.0% | -1.36 | outliers_z10,duplicate_columns | standard scaling |
| reg_num_Bike_Sharing_Demand |  | reg | 10427 | 6 | 5.41 | 0 | 0 | 1.5% | 0.0% | 1.28 |  | standard scaling |
| reg_num_Brazilian_houses |  | reg | 6415 | 8 | 79.18 | 5 | 0 | 3.3% | 0.0% | 0.30 | extreme_outliers_z50,heavy_tails | standard scaling |
| reg_num_MiamiHousing2016 |  | reg | 8359 | 13 | 11.83 | 1 | 0 | 0.1% | 0.0% | 0.74 | outliers_z10 | standard scaling |
| reg_num_abalone | yes | reg | 2506 | 7 | 22.83 | 1 | 0 | 0.0% | 0.0% | 1.11 | outliers_z10,heavy_tails | standard scaling |
| reg_num_cpu_act |  | reg | 4915 | 21 | 47.66 | 13 | 0 | 0.0% | 0.0% | -3.42 | outliers_z10,heavy_tails,skewed_target | standard scaling |
| reg_num_delays_zurich_transport | yes | reg | 3279345 | 8 | 14.03 | 1 | 0 | 99.9% | 0.0% | -0.87 | outliers_z10,heavy_tails,many_duplicate_rows | standard scaling |
| reg_num_diamonds |  | reg | 32364 | 6 | 46.22 | 4 | 0 | 3.9% | 0.0% | 0.12 | outliers_z10,heavy_tails | standard scaling |
| reg_num_elevators |  | reg | 9959 | 16 | 10.06 | 1 | 0 | 0.0% | 0.0% | 2.42 | outliers_z10,skewed_target | standard scaling |
| reg_num_house_16H | yes | reg | 13670 | 16 | 90.22 | 6 | 0 | 0.0% | 0.0% | -3.43 | extreme_outliers_z50,heavy_tails,skewed_target,target_outliers | standard scaling |
| reg_num_house_sales |  | reg | 12967 | 15 | 41.33 | 5 | 0 | 0.0% | 0.0% | 0.43 | outliers_z10,heavy_tails | standard scaling |
| reg_num_houses |  | reg | 12384 | 8 | 30.46 | 4 | 0 | 0.0% | 0.0% | -0.17 | outliers_z10,heavy_tails | standard scaling |
| reg_num_medical_charges | yes | reg | 97839 | 3 | 64.83 | 3 | 0 | 0.0% | 0.0% | 0.88 | extreme_outliers_z50,heavy_tails | standard scaling |
| reg_num_nyc-taxi-green-dec-2016 | yes | reg | 349101 | 9 | 98.84 | 2 | 0 | 0.6% | 0.0% | -0.00 | extreme_outliers_z50,heavy_tails | standard scaling |
| reg_num_pol |  | reg | 9000 | 26 | 20.84 | 14 | 0 | 0.1% | 0.0% | 0.92 | outliers_z10,heavy_tails | standard scaling |
| reg_num_sulfur |  | reg | 6048 | 6 | 14.47 | 1 | 0 | 0.0% | 0.0% | 6.73 | outliers_z10,heavy_tails,skewed_target,target_outliers | standard scaling |
| reg_num_superconduct | yes | reg | 12757 | 79 | 9.37 | 0 | 0 | 23.5% | 0.0% | 0.86 | heavy_tails,many_duplicate_rows | standard scaling |
| reg_num_wine_quality |  | reg | 3898 | 11 | 17.04 | 5 | 0 | 11.6% | 0.0% | 0.19 | outliers_z10,heavy_tails,many_duplicate_rows | standard scaling |
| reg_num_yprop_4_1 |  | reg | 5331 | 42 | 37.69 | 26 | 0 | 0.6% | 0.0% | -2.23 | outliers_z10,heavy_tails,skewed_target,target_outliers | standard scaling |

## Central sanity

| dataset | metric | constant | boosting reference | standard (1e-3) | clip (1e-3) | quantile (1e-3) | standard (1e-4) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| clf_num_Bioresponse | MCC | 0.000 | 0.563 | 0.490 | 0.443 | 0.506 | 0.437 |
| reg_cat_delays_zurich_transport | SMAPE | 0.951 | 0.968 | 0.964 | 0.964 | 0.944 | 0.956 |
| reg_num_abalone | SMAPE | 0.243 | 0.157 | 0.189 | 0.189 | 0.184 | 0.317 |
| clf_cat_electricity | MCC | 0.000 | 0.764 | 0.644 | 0.648 | 0.665 | 0.607 |
| reg_cat_Mercedes_Benz_Greener_Manufacturing | SMAPE | 0.098 | 0.053 | 0.059 | 0.057 | 0.056 | 0.076 |
| clf_num_covertype | MCC | 0.000 | 0.629 | 0.674 | 0.671 | 0.665 | 0.593 |
| reg_num_delays_zurich_transport | SMAPE | 0.951 | 0.960 | 0.939 | 0.929 | 0.930 | 0.957 |
| reg_cat_visualizing_soil | SMAPE | 0.769 | 0.006 | 0.026 | 0.026 | 0.027 | 0.089 |
| clf_num_eye_movements | MCC | 0.000 | 0.243 | 0.150 | 0.133 | 0.174 | 0.154 |
| reg_cat_Allstate_Claims_Severity | SMAPE | 0.086 | 0.055 | 0.057 | 0.057 | 0.058 | 0.058 |
| reg_num_superconduct | SMAPE | 0.987 | 0.371 | 0.441 | 0.445 | 0.452 | 0.553 |
| reg_num_medical_charges | SMAPE | 0.050 | 0.006 | 0.005 | 0.006 | 0.005 | 0.005 |
| clf_cat_covertype | MCC | 0.000 | 0.691 | 0.697 | 0.704 | 0.636 | 0.612 |
| reg_cat_SGEMM_GPU_kernel_performance | SMAPE | 0.202 | 0.002 | 0.004 | 0.004 | 0.007 | 0.010 |
| clf_num_MiniBooNE | MCC | 0.000 | 0.874 | 0.867 | 0.869 | 0.864 | 0.832 |
| reg_cat_house_sales | SMAPE | 0.032 | 0.010 | 0.012 | 0.012 | 0.012 | 0.013 |
| clf_cat_eye_movements | MCC | 0.000 | 0.273 | 0.198 | 0.201 | 0.214 | 0.125 |
| clf_num_electricity | MCC | 0.000 | 0.731 | 0.542 | 0.544 | 0.565 | 0.486 |
| reg_num_house_16H | SMAPE | 0.058 | 0.032 | 0.038 | 0.039 | 0.037 | 0.041 |
| reg_num_nyc-taxi-green-dec-2016 | SMAPE | 0.548 | 0.447 | 0.487 | 0.473 | 0.491 | 0.493 |

MiniBooNE standard MCC at 1e-3, with sentinel rows: 0.836; without sentinel rows: 0.867.

## Reproduce

Outputs go to a scratch directory first, because the scripts record git_dirty and files written inside the tree would mark the next run dirty.

```bash
out=$(mktemp -d)
sed -n "/^datasets=(/,/^)/p" scripts/run_full_experiments.sh | tr -d "'" | grep -v '[()]' > "$out"/names.txt
.venv/bin/python scripts/select_dataset_tiers.py --tier 20 < "$out"/names.txt > "$out"/tier20.txt
printf '%s\n' clf_num_MiniBooNE > "$out"/miniboone.txt
.venv/bin/python scripts/audit_datasets.py --names "$out"/names.txt --tier20 "$out"/tier20.txt --out-json "$out"/dataset_audit.json --out-csv "$out"/dataset_audit.csv
uv sync --frozen --extra ml
.venv/bin/python scripts/audit_central_sanity.py --names "$out"/tier20.txt --hpo-dir results/hyperparameter_optimization --out "$out"/central_sanity.jsonl
.venv/bin/python scripts/audit_central_sanity.py --names "$out"/miniboone.txt --hpo-dir results/hyperparameter_optimization --keep-sentinel-rows --out "$out"/central_sanity_keep_sentinel.jsonl
uv sync --frozen
cp "$out"/dataset_audit.json "$out"/dataset_audit.csv "$out"/central_sanity.jsonl "$out"/central_sanity.jsonl.provenance.json "$out"/central_sanity_keep_sentinel.jsonl "$out"/central_sanity_keep_sentinel.jsonl.provenance.json docs/audit/
.venv/bin/python scripts/render_dataset_audit.py --audit-json docs/audit/dataset_audit.json --sanity docs/audit/central_sanity.jsonl --sanity-before docs/audit/central_sanity_keep_sentinel.jsonl --out docs/dataset_preprocessing_audit.md
```
