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
- **Status:** done (pipeline audit did not meet the Gate 2 near-chance criterion)
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
