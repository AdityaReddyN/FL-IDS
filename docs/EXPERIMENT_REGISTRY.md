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
- **Data version:** sequences_v2 (regenerated into a new directory, original untouched)
- **Method / model:** LSTM, hidden 64, 1 layer, dropout 0.1, lr 1e-3, bs 256, patience 5
- **Seeds:** 42
- **Key results:** test accuracy 0.664533; macro-F1 0.648890; normal-data FPR
  0.726333; best validation macro-F1 0.652434 at epoch 9. Exact match with
  `results/centralized_lstm/baseline_h64_l1_seed42/` metrics and confusion matrix.
- **Result files:** `results/E-001/run1/config.json`, `test_metrics.json`,
  `history.csv`, `confusion_matrix.csv`, and `test_predictions.csv`.
- **Conclusion / caveats:** The baseline is reproducible for seed 42. It is a
  balanced, ad hoc v2 synthetic benchmark only; its 72.63% normal-data FPR is
  unsuitable as an operational IDS result.
