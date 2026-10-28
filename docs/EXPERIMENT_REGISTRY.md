# EXPERIMENT_REGISTRY.md

Register BEFORE running (status `planned`), update after. Append-only except for
the status/result fields of the entry itself. Numbers must be copied from result
files, never estimated.

## Template

```
### E-### — Short title
- **Status:** planned | running | done | failed | invalid
- **Date:** 
- **Phase:** 
- **Hypothesis / purpose:** 
- **Data version:** (e.g. sequences_v3, partition=geo_grid_k5)
- **Method / model:** 
- **Config path:** results/E-###/<run>/config.json
- **Seeds:** 
- **Git commit:** 
- **Key results:** (mean ± CI; primary metric; FPR on normal)
- **Result files:** 
- **Conclusion / caveats:** 
```

---

### E-001 — Reproduce v2 centralized LSTM baseline
- **Status:** done
- **Phase:** 0
- **Purpose:** Confirm the pipeline reproduces; compare with the earlier run in `results/centralized_lstm/`.
- **Data version:** original `data/sequences_v2`; its train/val/test X and y arrays
  and train client IDs equal `data/reproductions/phase0/sequences_v2_seed42` exactly.
- **Method / model:** LSTM, hidden 64, 1 layer, dropout 0.1, lr 1e-3, bs 256, patience 5
- **Seeds:** 42
- **Environment:** CPU; torch 2.14.0+cpu (both recorded in `run1/config.json`).
  Python version is not stored in that config; Python 3.12.14 was observed during
  Phase 0 validation, but is not verified as the training-process version.
- **Key results:** test accuracy 0.664533; macro-F1 0.648890; normal-data FPR
  0.726333; best validation macro-F1 0.652434 at epoch 9. Exact match with
  `results/centralized_lstm/baseline_h64_l1_seed42/` metrics and confusion matrix.
- **Result files:** `results/E-001/run1/config.json`, `test_metrics.json`,
  `history.csv`, `confusion_matrix.csv`, and `test_predictions.csv`.
- **Prediction SHA-256:** `16F1660F45C37FFF7CEF6CFBB9AA5671430F1ADA3638F546F6D88850F332430D`;
  identical to `results/centralized_lstm/baseline_h64_l1_seed42/test_predictions.csv`.
- **Conclusion / caveats:** Single-seed, balanced, ad hoc v2 synthetic benchmark;
  not an operational IDS result.

### E-002 — Phase 2 v3 sequence and shortcut pipeline validation
- **Status:** done (pipeline audit did not meet the Gate 2 near-chance criterion); **PILOT-DERIVED (D-036): computed on the seed-42 pilot; not a result, not for the paper**
- **Date:** 2026-10-23
- **Phase:** 2
- **Hypothesis / purpose:** Build sequence arrays from the verified seed-42 Stage C tables using the fixed aircraft split, train-only preprocessing, explicit missing masks, missingness-matched binary-balanced train indices, and unchanged realistic-prevalence validation/test splits; run natural and conditioned missingness, within-segment-position, and per-feature-summary shortcut baselines.
- **Data version:** `data/attack_generation_v3/stage1_seed_42_retry4` -> initial `data/sequences_v3/seed_42`, intermediate `data/sequences_v3/seed_42_missingness_matched`, final `data/sequences_v3/seed_42_phase2`
- **Method / model:** Deterministic sequence builder; CPU logistic-regression shortcut diagnostics (no detector-performance claim)
- **Config path:** `data/sequences_v3/seed_42_phase2/config.json`; audit result `results/E-002/shortcut_audit_seed42_final.json`
- **Seeds:** 42
- **Git commit:** `957a262`; builder worktree was dirty, with module/script SHA-256 values recorded in the dataset config.
- **Key results:** Final validation: missingness-only ROC-AUC 0.417674 natural and 0.507331 on the 258-window matched slice; within-segment-position ROC-AUC 0.507595; per-feature-summary ROC-AUC 0.602075 natural and 0.604531 matched. Matched slice: 129 normal + 129 attack. Dataset counts: train 170,767; val 37,712; test 37,721; balanced-train index 1,000 (500 per binary class). These are pipeline diagnostics copied from `shortcut_audit_seed42_final.json` and the dataset manifest.
- **Result files:** `results/E-002/shortcut_audit_seed42_final.json`; earlier, superseded diagnostic `shortcut_audit_seed42.json`; matched-view diagnostic `shortcut_audit_seed42_conditioned.json`; `data/sequences_v3/seed_42_phase2/manifest.json` and `config.json` (ignored, not committed).
- **Conclusion / caveats:** Pipeline validation only on one seed and a two-hour decoded-state-vector source with synthetic labels. Matching makes missingness-only and position-only audits near chance, but per-feature summaries remain informative; realistic val/test retain natural prevalence/missingness. Gate 2 is not passed, and no Phase 3 training or scientific result is authorized by this run.

### E-003 — Initial binary LSTM on v3 windows
- **Status:** done; **PILOT-DERIVED (D-036): computed on the seed-42 pilot; not a result, not for the paper**
- **Date:** 2026-10-23
- **Phase:** 3 (pipeline validation)
- **Hypothesis / purpose:** Establish a reproducible learned binary detector baseline after human authorization to proceed past Gate 2, retaining the known E-002 shortcut caveat.
- **Data version:** `data/sequences_v3/seed_42_phase2` (two-hour source, synthetic labels, realistic-prevalence val/test; ambiguous windows excluded)
- **Method / model:** Small CPU LSTM; balanced binary training indices; select checkpoint by validation macro-F1 at threshold 0.5; report ROC-AUC, PR-AUC, normal FPR, and confusion matrix on realistic test data.
- **Config path:** `results/E-003/binary_lstm/seed<k>/config.json`
- **Seeds:** 0-4
- **Git commit:** `f52350a`; each result config records the code commit and library versions.
- **Key results:** Across seeds 0-4, test ROC-AUC 0.5742 ± 0.0276 and PR-AUC 0.00443 ± 0.00048 (mean ± 95% t-interval half-width across seeds). Macro-F1 at threshold 0.5 is 0.4380 ± 0.0542; normal FPR at threshold 0.5 is 0.2245 ± 0.1654. Each test split has 37,683 non-ambiguous windows (37,566 normal, 117 attack). Values aggregated from the five per-seed `metrics.json` files.
- **Result files:** `results/E-003/binary_lstm/seed<k>/metrics.json`, `history.csv`, `test_predictions.csv`; a same-seed checkpoint-preserving repeat is at `seed0_checkpointed/` and includes `model_state.pt`.
- **Conclusion / caveats:** Low discrimination; no support for the requested 0.9 ROC-AUC. Pipeline validation only on one two-hour source and synthetic labels, with a known summary-statistic shortcut signal. No test-set tuning. Five per-seed configs, metrics, histories, and predictions are under ignored `results/E-003/binary_lstm/`. `seed0_checkpointed/` was trained with commit `8afab0b`; its result metrics exactly match the original seed-0 run, and its 28,293-byte CPU state dict was successfully loaded for verification.

### E-004 — Stage C seed-42 attack generation PILOT (`stage1_seed_42_retry4`)
- **Status:** done; **PILOT (D-036) — must not be used for evaluation or the paper**
- **Date:** 2026-10-22 (generated); registered retroactively 2026-10-26
- **Phase:** 1
- **Hypothesis / purpose:** End-to-end Stage C generation smoke run of the multi-overlay writer.
- **Data version:** input cleaned table content fingerprint `d05f15d7...f018e3`; output `data/attack_generation_v3/stage1_seed_42_retry4/` (ignored)
- **Method / model:** 7 overlays, all tier `moderate`, `tau` 0.005, `duration_seconds` 120, `onset_mode` `linear_mix`, `episodes_per_segment` 1, `min_gap_seconds` 600; altitude overlay `altitude_variant` `baro_only`; manifest `dataset_mode` `uniform_per_subairspace`. Gate 1b calibration not run; no 600/900 s episodes.
- **Config path:** `data/attack_generation_v3/stage1_seed_42_retry4/config.json` (config SHA-256 `e5faeeba...a531b`)
- **Seeds:** 42
- **Git commit:** `72958b07de012a15520788aaa445aabf6591878a`; `git_dirty` false
- **Key results (from `manifest.json`):** table rows: attacked_rows 2,970,285; step_labels 2,970,285; windows 246,200; segments 21,389; overlay_selections 149,723; episodes 263; modified_row_provenance 3,142; rejected_candidates 63. Merged: 263 accepted episodes, 3,156 attack rows, 2,630 effective rows. Accepted by family: altitude_constant_deviation 59; random_gaussian_deviation 49; freeze_fixed_value 44; replay_partial_field 43; constant_deviation 39; replay_full_field 29; gradual_deviation 0. Rejections: insufficient_effective_rows 48 (all gradual); no_measurable_change 7 (freeze 6, replay_partial 1); overlay_conflict 4 (replay_full 2, constant 1, freeze 1); no_freeze_anchor 3; altitude_out_of_range 1. Realized tau (chosen/eligible): altitude 0.00606, constant 0.00407, freeze 0.00553, gradual 0.00501, gaussian 0.00511, replay_full 0.00386, replay_partial 0.00575.
- **Result files:** `manifest.json`, eight Parquet tables, `plausibility_report.json`, `plots/` in the run directory.
- **Conclusion / caveats:** Structural validators passed only; no semantic validation against the source. `episodes.speed_band` is `unknown` and `freeze_anchor_source_row_id` null for all episodes; `onground` NaN coerced to True. Pilot scale; one tier/duration/variant; zero gradual episodes. Directories `stage1_seed_42`, `_retry1`, `_retry2`, `_retry3` are incomplete partial attempts. All are immutable.

### E-005 — Kind A per-cell evaluation generation (HDD subset)
- **Status:** planned
- **Date:** 2026-10-27
- **Phase:** 1 (S7, D-045)
- **Hypothesis / purpose:** Generate the per-cell evaluation dataset (D-039 kind A) as ONE joint quota run (one overlay per segment, resolved in plan order) on the aircraft-hash working subset of `hdd_clean_v1`, for per-family/tier/duration recall with boundary vs interior-only strata.
- **Data version:** `data/processed/hdd_clean_v1_subset_<frac>pct.parquet` (subset content_fingerprint recorded at run time); split `data/processed/hdd_clean_v1/split_aircraft.json`.
- **Method / model:** `scripts/run_stage7.py` → `generate_attack_v3.py --plan plan_A_per_cell_eval.yaml --conflict-order plan --input <subset>`; ratio tiers (D-044); quota mode.
- **Run plan:** `configs/run_plans/plan_A_per_cell_eval.yaml` (sha256 e6bc2ff71db88888…); 25-overlay joint quota run, plan-order conflict resolution; approval `configs/run_plans/approved_cells_A.json` (D-046)
- **Seeds:** 42
- **Git commit:** (filled at generation; writer records it + git_dirty=false)
- **Key results:** (from manifest after the human run)
- **Result files:** `data/attack_generation_v3/stage7_A/`; validation `results/stage7/validate_A.json`
- **Conclusion / caveats:** Subset-scale; `attacked_rows` written 1:1 with the source (full-scale 'accepted-segments-only' amendment deferred, D-045). Not run yet.

### E-006 — Kind B mixed realistic-prevalence generation (HDD subset)
- **Status:** planned
- **Date:** 2026-10-27
- **Phase:** 1 (S7, D-045)
- **Hypothesis / purpose:** Generate the mixed realistic-prevalence set (D-039 kind B): all seven families, Bernoulli tau=0.005, one overlay per segment.
- **Data version:** same subset as E-005; split `hdd_clean_v1/split_aircraft.json`.
- **Method / model:** `generate_attack_v3.py --plan plan_B_mixed_realistic.yaml --input <subset>` (lexicographic merge).
- **Run plan:** `configs/run_plans/plan_B_mixed_realistic.yaml` (sha256 09fee4d6505009ab…)
- **Seeds:** 42
- **Git commit:** (filled at generation)
- **Key results:** (from manifest)
- **Result files:** `data/attack_generation_v3/stage7_B/`; `results/stage7/validate_B.json`
- **Conclusion / caveats:** Subset-scale; attacked_rows 1:1 with source (D-045). Not run yet.

### E-007 — Kind C Track B training generation (HDD subset)
- **Status:** planned
- **Date:** 2026-10-27
- **Phase:** 1 (S7, D-045)
- **Hypothesis / purpose:** Generate the mixed Track B training set (D-039 kind C): all families, larger tau (0.05) for enough attacked windows; train aircraft only via the fixed split.
- **Data version:** same subset as E-005; split `hdd_clean_v1/split_aircraft.json`.
- **Method / model:** `generate_attack_v3.py --plan plan_C_trackB_training.yaml --input <subset>`.
- **Run plan:** `configs/run_plans/plan_C_trackB_training.yaml` (sha256 1ef62b2b0187f2ee…)
- **Seeds:** 42
- **Git commit:** (filled at generation)
- **Key results:** (from manifest)
- **Result files:** `data/attack_generation_v3/stage7_C/`; `results/stage7/validate_C.json`
- **Conclusion / caveats:** Subset-scale; attacked_rows 1:1 with source (D-045). Not run yet.
