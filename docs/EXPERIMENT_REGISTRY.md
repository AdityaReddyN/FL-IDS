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
