# ROADMAP.md

Tick boxes as tasks complete. Do not start a phase until the previous gate is
approved by the human. Add new tasks freely, but never delete old ones (strike
through with `~~` and explain in PROGRESS_LOG).

**Current phase: 1 — foundation implemented (D-020); attack operations not started**

## Phase 0 — Housekeeping and baseline reproduction
- [x] `requirements.txt` with pinned versions
- [x] `README.md` explaining how to run each stage
- [x] `tests/` skeleton + CI-free `pytest` runs
- [x] Move v1 scripts (`build_sequence.py`, `validate_sequence.py`) to `scripts/legacy/`
- [x] Re-run `build_dataset.py` -> `validate_dataset.py`; record dataset facts in PROJECT_CONTEXT
- [x] Re-run `build_sequences_v2.py` (to a new dir, not overwriting) + `validate_sequences_v2.py`
- [x] Re-run `train_centralized_lstm.py`; register as E-001 and compare with the earlier run
- [x] Read-only normal-window diagnostic: document weak v2 baseline (72.63% normal FPR,
  28.37% position-spoof recall), frozen/on-ground prevalence, and two unverified
  causal hypotheses for later shortcut auditing
- [x] **GATE 0: human approves**

## Phase 1 — Row-level attack generation v3
- [x] D-004--D-009 approved: Eq. 10 sweep, Eq. 11--13 amplitude/noise/stealth,
  Track A novelty primary and Track B upper bound, correct replay naming,
  staged ghost/DoS scope, and episode-level injection.
- [x] Design doc: `docs/attack_v3_design.md` (Draft 4: decoupled truth from detectability, post-hoc reporting strata, 600s/900s long-episode settings for interior window feasibility, train-only thresholds, separate 15+ m/s vertical-rate treatment; human review pending before code)
- [x] Draft `configs/attack_v3_stage1.yaml` (Draft 4: proposed tolerances, regions, quotas,
  tiers, long episodes, train-only p95 thresholds, and reproducibility settings; human review pending before code)
- [x] Read-only Stage 1 calibration/feasibility report: 5-degree grid/density,
  split eligibility and capacity, residuals, replay-change candidates, and
  geoaltitude outliers (reviewed thresholds remain proposed)
- [x] Extended read-only calibration JSON (`docs/calibration_v3_stage1.json`, report_version 4):
  train-only residual thresholds, segment length distribution (12,616 segments >= 600s),
  long-episode interior window yields (600s: 2.50, 900s: 5.50), unique aircraft capacity by speed band,
  corrected oracle boundary benchmarks under 3-step ramp and abrupt onsets, and FPR on maneuver-matched controls (all proposed per D-019)
- [x] Foundation modules in `src/flids/attacks/`: YAML approval gate, natural keys,
  content/schema fingerprints, deterministic segment/episode seeding, fixed aircraft
  split access, five output schemas, manifest skeleton; synthetic tests (D-020)
- [x] Read-only real-data foundation check script written
  (`scripts/check_foundation_on_real_data.py`; not yet run)
- [ ] Attack framework in `src/flids/attacks/` (base class, target selection: random/area/neighbour)
- [ ] Constant deviation
- [ ] Random Gaussian deviation
- [ ] Increased/gradual deviation
- [ ] (optional) non-linear, zoom, changeable deviation
- [ ] Delayed replay (300 s, same-aircraft lookback)
- [ ] Amplitude calibration from historical statistics + stealth tiers
- [ ] Attack proportion parameter + sweep support
- [ ] Per-row provenance (original/modified values, episode id, params, source row)
- [ ] Rejected-candidate log
- [ ] Physical plausibility validator + report
- [ ] `manifest.json`
- [ ] Unit tests (determinism, no leakage across aircraft, delay correctness, no edits outside intervals)
- [ ] Visual sanity plots (example trajectories before/after)
- [ ] **GATE 1: human reviews manifest, report, plots**

## Phase 2 — Sequence dataset v3 + shortcut audit
- [ ] Window builder from attacked row table, per-step + per-window labels
- [ ] Aircraft-level split; source windows kept together; train-only preprocessing
- [ ] Balanced train set + realistic-prevalence val/test sets
- [ ] Binary and multiclass labels
- [ ] Remove v2 shortcuts (placement, missingness parity)
- [ ] Shortcut audit script + results logged
- [ ] Delta features: derive only within segments; retain undefined deltas at starts/gaps.
- [ ] No median imputation inside windows; use train-only preprocessing or explicit masks.
- [ ] Retain `onground` and a configured stale-data flag as provenance/diagnostic fields.
- [ ] Specify and audit distinguishable true replay and fixed-value freeze labels.
- [ ] Audit `contact_lag_seconds` for label leakage before admitting it as a model feature.
- [ ] **GATE 2**

## Phase 3 — Centralized baselines
- [ ] Classical baseline (LR / RF on engineered features)
- [ ] LSTM, GRU, 1D-CNN, small Transformer
- [ ] (optional) autoencoder trained on normal only
- [ ] Unified metrics module (PR-AUC, recall@FPR, latency, etc.)
- [ ] 5 seeds each, CI table
- [ ] **GATE 3**

## Phase 4 — Client partitioning
- [ ] IID, geographic grid, aircraft-group, Dirichlet label skew, quantity skew
- [ ] Heterogeneity report per partition
- [ ] **GATE 4**

## Phase 5 — FL experiments
- [ ] FL simulation loop (record Flower vs custom decision in DECISIONS.md)
- [ ] Local-only baseline
- [ ] FedAvg, FedProx, FedAdam (+ SCAFFOLD optional)
- [ ] Personalization (fine-tune, FedPer-style)
- [ ] Communication cost accounting
- [ ] Full grid: algorithms x partitions x seeds
- [ ] **GATE 5**

## Phase 6 — Robustness and privacy
- [ ] Label-flip and model-poisoning clients (10/20/30%)
- [ ] Median, trimmed mean, Krum aggregation
- [ ] (optional) DP / update compression
- [ ] Held-out region and unseen-attack evaluation
- [ ] Contaminated Track A novelty-training scenario with a declared attack-row fraction
- [ ] **GATE 6**

## Phase 7 — Evaluation and figures
- [ ] `make_tables.py`, `make_figures.py` regenerate everything from results
- [ ] Ablations (window length, stealth, proportion, #clients, local epochs)
- [ ] CIs / significance tests
- [ ] **GATE 7**

## Phase 8 — Paper support
- [ ] `docs/PAPER_OUTLINE.md` with claims-evidence matrix
- [ ] `docs/LIMITATIONS.md`
- [ ] Related-work table
- [ ] **GATE 8**
