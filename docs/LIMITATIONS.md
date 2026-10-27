# Current limitations

Updated 2026-10-26 (D-036/D-037). Living document; keep it current.

## Data source
- The evaluated source covers about two hours of OpenSky data on 2017-06-05
  (00:00:00–01:59:50 UTC; 2,970,285 rows, 14,279 aircraft). Temporal and
  geographic support is limited.
- Inputs are decoded OpenSky state vectors, not raw 112-bit ADS-B messages.
- `geoaltitude` contains glitches/outliers; altitude attacks and residual
  thresholds must account for them (see `docs/attack_v3_design.md`).
- `onground` can be missing; the current assembler coerces NaN to True
  (fix pending, W2).
- The HDD archives (`data/hdd_data`, 90 hourly archives, Nov/Dec 2019) are
  unaudited: schema consistency, cadence (README suggests ~1 Hz versus the
  ~10 s rows the attack code assumes), duplicates, and coverage are unverified.

## Attack synthesis
- Attacks are synthetic data-layer manipulations of decoded state vectors.
  There are no RF, bit-level, signal-strength, receiver-processing, or
  multilateration effects; replay is stale-track/data-layer replay only.
- `tau` is a per-eligible-segment Bernoulli selection probability, not Li et
  al.'s Eq. 10 density/strength term (D-037). No Eq. 10 implementation is
  claimed.
- Ghost injection and DoS are not implemented.
- Physical plausibility reports are descriptive; no plausibility cutoffs have
  been approved.
- Per-cell medians used for altitude/position statistics are not
  antimeridian-aware.

## Generation status
- Only pilot-scale generation exists: `stage1_seed_42_retry4` (E-004) is one
  tier (`moderate`), one tau (0.005), one duration (120 s), `baro_only`
  altitude, 263 accepted episodes, and zero gradual episodes (D-036). Long
  (600/900 s) episodes were never generated and Gate 1b calibration was not
  run. The pilot must not be used for evaluation.
- In the pilot, `episodes.speed_band` is `unknown` and
  `freeze_anchor_source_row_id` is null for every episode.

## Calibration (Gate 1b, HDD)
- The Gate 1b calibration (`results/gate1b_calibration_v2.json`, D-042) computes
  the single-step boundary oracle (constant/Gaussian/freeze/partial-replay) and
  per-split capacity, but **not** the integrated-residual oracle over k = 5, 10,
  29 steps. Gradual deviation's per-step drift is sub-threshold, so its
  detectability only accrues cumulatively; without the integrated oracle, when
  within a gradual (or long) episode it becomes detectable is not yet calibrated
  on the HDD source. This gap does not block generation (S7); it is scheduled as
  a reference detector and for the post-hoc "interior-with-residual" stratum in
  Phase 3 (S8/S9). Single-step boundary recall is near a step function at each
  band's train p95 threshold, and the real ramp (first step 0.25× magnitude)
  trips the boundary only near ~4× the threshold.
- Horizontal constant-deviation tiers are defined by a ratio r to the train-only
  band p95 (D-043), not fixed meters; the r values are approved from the
  confirmatory r-grid run before generation. Gradual deviation keeps fixed
  meters: its per-step drift is sub-threshold, so a single-step oracle cannot see
  it and its detectability must be read from the (deferred) integrated-residual
  oracle. The oracle recalls here are per-step (boundary) quantities; per-window
  detectability (how many windows in an episode are flagged, and interior-only
  windows) is a separate post-hoc stratum computed at Phase 2/3, not by Gate 1b.

## Results
- E-002 (shortcut audit) and E-003 (binary LSTM, mean test ROC-AUC 0.5742)
  are PILOT-DERIVED (D-036) and are not results. E-002's per-feature-summary
  shortcut signal (ROC-AUC 0.6021 natural / 0.6045 matched) remains a design
  warning for future datasets.
- No federated experiment, region hold-out, or multi-seed model comparison
  exists. OpenSky does not identify receivers; grid partitions can only be
  called simulated geographic clients.
- Labels are synthetic; nothing here establishes operational aviation-IDS
  performance. Never tune on the test set or promise a target score.
- The external `context.docx` describes different data and unverified metrics;
  none of it is attributed to this repository.
