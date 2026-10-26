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
