# Current limitations

Updated 2026-10-23 (Phase 3 pipeline validation; D-034/D-035).

- The current evaluated source is decoded OpenSky state vectors, not raw ADS-B
  messages. Labels are synthetic data-layer simulations and do not establish
  operational aviation-IDS performance, RF replay fidelity, or message-layer
  security.
- Existing v3 data covers about two hours on 2017-06-05. It has limited
  temporal/geographic support. E-003 is a five-seed binary LSTM pipeline check:
  mean test ROC-AUC 0.5742 (95% t-interval half-width 0.0276), PR-AUC 0.00443,
  macro-F1@0.5 0.4380, normal FPR@0.5 0.2245. These figures do not meet the
  requested ROC-AUC 0.9 and are not scientific evidence.
- E-002's per-feature-summary shortcut ROC-AUC remains 0.6021 on natural
  validation / 0.6045 on the missingness-matched slice. The audit did not pass
  its near-chance summary-stat criterion; Phase 3 progression was authorized
  with the caveat retained (D-034).
- Seed-42 generation has no accepted gradual-deviation episodes (all 48
  selected candidates were rejected under the approved minimum-effective-row
  rule). Its class is declared but absent in that realization.
- HDD inventory: 90 hourly archives (~11.962 GiB) across four weekly dates in
  Nov/Dec 2019, not four contiguous complete days. One sampled inner CSV
  header matches decoded-state-vector fields, and its README describes roughly
  1 Hz. All-hour schema consistency, actual cadence, duplicate behavior,
  missingness, geography, and aircraft recurrence remain unverified. Do not
  feed this source to the current roughly 10-second assembler unchanged.
- The attached `context.docx` describes different January/February data and
  reports unverified metrics/methods; those are not attributed to the checked-in
  HDD archives or this repository.
- No aircraft-cluster confidence intervals, multiclass model comparison,
  held-out-region evaluation, or federated experiment has been completed on the
  HDD source. OpenSky does not identify actual receivers; grid partitions can
  only be described as simulated geographic clients.
- Physical plausibility reports are descriptive. State vectors cannot establish
  raw-message authentication, signal strength/receiver processing, bit-level
  effects, or multilateration behavior.
- Every new result remains pipeline validation until the source audit,
  leakage/shortcut review, and phase-specific human gates are addressed. Never
  tune on the test set or promise a target score.
