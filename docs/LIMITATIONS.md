# Current limitations

Updated 2026-10-23 (Phase 2 pipeline validation; E-002).

- The source is decoded OpenSky state vectors, not raw ADS-B messages. Attack
  labels simulate data-layer effects; they do not establish RF/message replay
  fidelity or operational aviation-IDS performance.
- The source covers about two hours on 2017-06-05 and has limited temporal and
  geographic support for generalization or receiver-level federated-learning
  claims.
- Stage C seed 42 produced 263 accepted episodes in six attack families.
  Gradual deviation has no accepted episode: all 48 selected candidates were
  rejected under the approved 120-second/five-effective-row rule. The gradual
  multiclass ID is declared but has zero windows.
- Stage C physical-plausibility checks are descriptive. Raw-message effects,
  receiver signal strength/processing, and multi-receiver multilateration are
  unavailable from these state vectors.
- Phase 2 currently has one generated realization/seed. The realistic
  validation/test splits retain natural prevalence and missingness. The
  missingness-matched audit slice is a diagnostic subset, not a replacement for
  realistic evaluation.
- E-002 is pipeline validation only. Position-only and missingness-only audits
  are near chance on the conditioned validation slice, but per-feature summary
  statistics remain informative (ROC-AUC 0.6045 conditioned; 0.6021 on natural
  validation). Gate 2 is not passed; whether this is expected attack signal or
  an unacceptable shortcut remains unresolved.
- `contact_lag_seconds` is kept outside model inputs pending a dedicated label
  leakage review. The 30-second stale-data flag threshold is an implementation
  choice.
- No Phase 3 detector training, multi-seed estimate, aircraft-cluster CI,
  held-out-test shortcut audit, or federated experiment has been completed for
  v3.
