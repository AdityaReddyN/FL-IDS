# PROJECT_CONTEXT.md

> **Current snapshot; history is in `PROGRESS_LOG.md`.** Updated 2026-10-23,
> Session 4p. Recheck branch, worktree, ignored outputs, and live configs before
> acting.

## Mission and scientific framing

The project studies federated-learning intrusion detection for ADS-B
surveillance data. Inputs are decoded OpenSky state vectors, not raw 112-bit
ADS-B messages. Attack labels are synthetic data-layer simulations; model
scores are not operational aviation-IDS evidence. Li et al. (2020) mappings or
numeric details not verifiable from the paper are implementation choices.

## Current state

- Branch at handoff: `phase1-generation`. Phase 1 seed-42 attack generation was
  accepted at Gate 1 (D-032); Phase 2 is built. The human authorized Phase 3
  despite the E-002 shortcut audit remaining informative (D-034). That is
  authorization to proceed, not an audit pass.
- E-002: summary-statistic shortcut ROC-AUC 0.6021 on natural validation and
  0.6045 on the missingness-matched slice; position and missingness controls
  are near chance only in their reported settings. Keep this caveat attached
  to downstream results.
- E-003: five-seed binary LSTM on the existing two-hour v3 sequence dataset;
  test ROC-AUC mean 0.5742 (95% t-interval half-width 0.0276), PR-AUC 0.00443,
  macro-F1@0.5 0.4380, and normal FPR@0.5 0.2245. Pipeline validation only;
  this does not meet the requested 0.9 ROC-AUC target. A seed-0 checkpoint is
  in ignored `results/E-003/binary_lstm/seed0_checkpointed/`.
- `data/hdd_data` inventory: 90 `.csv.tar` files, 11.962 GiB, spanning 90
  hourly archives across 2019-11-18, 2019-11-25, 2019-12-02 (18 hours), and
  2019-12-09. One sampled inner CSV has OpenSky decoded-state-vector columns;
  the embedded README says roughly 1 Hz. Actual cadence, all-file schema
  consistency, duplicate behavior, and coverage have not been audited.
- Phase 3/HDD workflow is documented in `docs/phase3_hdd_model_plan.md`.
  No HDD data has been cleaned, injected, windowed, or used for training.
  Existing attack/window code assumes roughly 10-second rows; do not apply it
  to the likely 1-Hz data until cadence is measured and semantics are resolved.
- No federated-learning implementation or actual receiver IDs exist. Geographic
  grid clients, if implemented, must be called simulated geographic clients.

## Data and immutable artifacts

The existing cleaned dataset has 2,970,285 rows, 14,279 aircraft, and 21,389
segments across 2017-06-05 00:00:00–01:59:50 UTC; it is approximately 10-second
sampled and uses a >30-second segment gap. The generated v3 sequence data is
`data/sequences_v3/seed_42_phase2/` (ignored): 30-row windows, stride 10,
aircraft-level 70/15/15 splits, train-only preprocessing, and natural
prevalence evaluation. Seed 42 has no accepted gradual-deviation episodes.

Never modify `data/raw/`, `data/processed/opensky_clean_v1.parquet`,
`data/sequences/`, `data/sequences_v2/`, or `results/centralized_lstm/`. Do not
commit datasets or weights. New derived data belongs in new versioned ignored
directories. Preserve any pre-existing untracked files.

## Processing and evaluation plan

1. Audit HDD archives read-only: schemas/types, rows and aircraft by hour,
   cadence, duplicates, missingness, geographic/time coverage, and aircraft
   recurrence. Do not generate attacks during this audit.
2. Stream tar/gzip inputs into a new versioned clean output, validate and hash
   source artifacts, normalize decoded state vectors, preserve missingness, and
   report conflicting duplicates. Determine cadence before choosing
   time-based semantics or deterministic resampling.
3. Assign aircraft to train/validation/test before windows; save and verify a
   disjoint split map. Use the clean pre-attack rows for eligibility and
   geographic assignment. Inject approved episode attacks in memory/derived
   output with original/modified values and row-level provenance. Keep each
   segment to one overlay, preserve rejections, and never use labels/provenance
   as model features.
4. Build windows within a segment and split. Fit imputation/scaling on unique
   training rows only. Keep realistic validation/test prevalence and report
   shortcut controls separately.
5. Compare logistic regression/random forest on engineered window summaries
   with LSTM, GRU, temporal 1D-CNN, and a small Transformer. Select using
   validation PR-AUC (binary) or macro-F1 (multiclass); calibrate fixed-FPR
   thresholds on validation normals. Evaluate locked test data once and run at
   least five seeds for reported estimates.
6. After centralized review, compare local-only/FedAvg and later methods using
   aircraft-contained client partitions and matched centralized controls.
   Position-grid partitions simulate geography; they are not receiver IDs.

The detail and open cadence decision are in `docs/phase3_hdd_model_plan.md`.
No metric target, including ROC-AUC 0.9, is guaranteed; do not tune against the
test split to reach it.

## Governing records

- Roadmap and gates: `docs/ROADMAP.md`; decisions: `docs/DECISIONS.md`.
- Experiment registration/results: `docs/EXPERIMENT_REGISTRY.md`.
- Session history: `docs/PROGRESS_LOG.md`; limitations: `docs/LIMITATIONS.md`.
- Attack mapping/design: `docs/attack_generation_methodology.md` and
  `docs/attack_v3_design.md`.
- New-chat navigation: `docs/CHAT_HANDOFF.md` (not authorization).
