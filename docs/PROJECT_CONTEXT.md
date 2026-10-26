# PROJECT_CONTEXT.md

> **Current snapshot; history is in `PROGRESS_LOG.md`.** Updated 2026-10-26
> (S0, D-036/D-037). Recheck branch, worktree, ignored outputs, and live configs
> before acting.

## Mission and scientific framing

The project studies federated-learning intrusion detection for ADS-B
surveillance data. Inputs are decoded OpenSky state vectors, not raw 112-bit
ADS-B messages. Attack labels are synthetic data-layer simulations; model
scores are not operational aviation-IDS evidence. Li et al. (2020) mappings or
numeric details not verifiable from the paper are implementation choices.

## Current state

- Branch: `phase1-generation`. **D-036 reclassified the seed-42 Stage C run
  (`stage1_seed_42_retry4`, E-004) as a PILOT** and superseded the D-032 Gate 1
  acceptance; Gate 1 is pending again. The pilot is one tier (moderate),
  τ=0.005, 120 s episodes, baro_only altitude, 263 accepted episodes, zero
  gradual episodes. It must not be used for evaluation, model selection, or any
  paper number.
- Phase 2 and Phase 3 were built on the pilot, so **E-002 and E-003 are
  PILOT-DERIVED (D-036), not results.** The D-034 Phase 3 authorization rested
  on pilot data and is suspended. No further Phase 2/3 work until the dataset
  plan is approved (S2 in `nextSteps.md`).
- E-002 kept as a design warning only: per-feature-summary shortcut ROC-AUC
  0.6021 natural / 0.6045 matched (did not pass the near-chance criterion).
- E-003 kept as a pipeline smoke test only: five-seed binary LSTM, mean test
  ROC-AUC 0.5742 on 117 test attack windows; uninterpretable on pilot data.
- Work now follows the staged plan in `nextSteps.md`, one stage per session.
  S0 (docs/supersession/hygiene) and S1 (source-independent code fixes) are
  done. S1 added: episode `speed_band` from median velocity and freeze
  `freeze_anchor_source_row_id`; nullable `onground` carried through (null →
  ineligible); OverlaySpec rejects < 5 effective rows (gradual@120s); run-plan
  YAML + `--plan`/`--onset-mode` CLI that refuses a silent pilot; manifest
  additions (elapsed/chunk seconds, resolved plan, window counts, per-split
  realized τ, per-overlay aircraft/window counts) + `--progress-log`; sequence
  builder refuses a dirty tree; D-038 canonical selection naming.
- S2 is implemented and awaiting approval: `quota.py` adds ranked two-pass
  quota selection (deterministic, chunk-independent, `fail_on_capacity_shortfall`
  with a per-cell shortfall table), wired through `--plan` quota entries, the
  writer (manifest `selection_mode`/`quota`), and a quota dry-run. The assembler
  was refactored to a shared `segment_selection` helper (goldens unchanged).
  Read-only `scripts/capacity_study.py` added (not run). **D-039 PROPOSES** a
  three-kind dataset plan (A per-cell evaluation, B mixed realistic-prevalence,
  C Track B training). D-040 records human approval of the D-039 structure
  (numeric params still open, set at S4/S6).
- S3 is implemented and awaiting a human run: read-only `scripts/audit_hdd_source.py`
  streams each `data/hdd_data/*.csv.tar` (resumable, never writes under
  `data/hdd_data`) and writes per-archive + `summary.json` reports across six
  areas (schema, time coverage, per-track cadence, aircraft recurrence, quality,
  10 s resampling estimate); pure helpers in `src/flids/data/hdd_audit.py`;
  `docs/hdd_audit_report_template.md` lists the S4 human decisions. Nothing was
  run on real data (the archives are not in this checkout). Next: human runs the
  audit and pastes `summary.json`; S4 is the human gate (source, resampling,
  split, confirm D-039).
- S4 decided (D-041): the full 90-archive audit (`results/hdd_audit_v1/`) found
  207,010,888 rows, 79,755 aircraft, 4 weekly dates, global coverage, every
  archive schema-matching, cadence ~10 s (not 1 Hz), 0 duplicate (icao24,time)
  rows, and 61% aircraft recurrence across dates. Chosen: HDD primary source,
  no resampling (existing ~10 s assembler applies), global hashed-`icao24`
  split. Velocity glitches (up to ~2974 m/s) flagged for the S5 clean. Next is
  S5 (build a new versioned cleaned HDD table + global split + validator).
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
