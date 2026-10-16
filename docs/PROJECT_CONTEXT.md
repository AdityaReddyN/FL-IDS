# PROJECT_CONTEXT.md

> **Snapshot, rewritten in place.** Keep it short and current. History belongs in
> `PROGRESS_LOG.md`. Last updated: 2026-10-17, Session 7.

## Goal
Publishable research paper on federated-learning-based intrusion detection for
ADS-B enabled systems, using OpenSky ADS-B data and synthetic attacks grounded
in Li et al. (2020), IET Information Security 14(5), doi:10.1049/iet-ifs.2018.5635.

## Current phase
Phase 1 extended-calibration review. Gate 0 approved; attack code is not authorized until the
human approves the revised `docs/attack_v3_design.md` and
`configs/attack_v3_stage1.yaml`.

## Data (VERIFY AND FILL IN during Phase 0 — values below are unverified)
- Source: OpenSky Network **decoded state vectors** (not raw 112-bit messages), ~10 s sampling.
- Raw files: `data/raw/*.csv` (believed to be two hourly files) — confirm count, date, time range.
- Cleaned table: `data/processed/opensky_clean_v1.parquet`
  - reproduction measured: 2,970,285 rows; 14,279 aircraft; 21,389 segments.
  - time range: 2017-06-05 00:00:00--01:59:50 UTC; cleaned-data bounding box:
    lat [-39.502227, 65.120389], lon [-155.835677, 175.842876].
  - missingness: lat/lon 900,624 (30.32%); velocity/heading 975,197 (32.83%);
    vertrate 884,474 (29.78%); baroaltitude 290,822 (9.79%); geoaltitude 1,157,834 (38.98%).
- Features: lat, lon, velocity, heading (sin/cos), vertrate, baroaltitude,
  geoaltitude + 7 binary missing flags. Segments split at >30 s gaps.

## Datasets built so far
| Version | Path | Windowing | Split | Classes | Status |
|---|---|---|---|---|---|
| v1 | `data/sequences/` | 30 / stride 10 | legacy | 5 synthetic | legacy, do not use |
| v2 | `data/sequences_v2/` | 30 / stride 10 | aircraft 70/15/15, train-only scaler | normal + 4 ad hoc attacks, balanced | immutable baseline |
| v3 | `data/sequences_v3/` | TBD | aircraft-level | TBD | not started |

## Attacks
- v2 attacks (ad hoc, NOT from the paper): position offset (lat ±0.15, lon ±0.20),
  velocity ±80 m/s, altitude ±2500 m, freeze/replay-like. Known to be trivially
  detectable and shortcut-prone.
- v3 plan (paper-grounded, partial): constant / Gaussian / gradual deviation,
  300 s delayed replay. Ghost injection and DoS deferred. Exact equations from
  Li et al. are unavailable; numeric ranges are implementation choices.
- `docs/attack_v3_design.md` and `configs/attack_v3_stage1.yaml` are
  extended-calibration review drafts only. Stage 1 is manipulation/replay, with
  shared eligibility versus attack-only effect conditions, boundary labels,
  ambiguous-window exclusion, maneuver-matched controls, segment-target eta,
  episode/aircraft-first quotas, and physical manipulation/altitude tiers.
  Uniform-per-sub-airspace is proposed as the primary FL dataset; ghost/DoS are
  Stage 2. No attack code exists or is authorized before approval.
- Read-only Stage 1 calibration: 260 occupied 5-degree cells; 60-second-cell rho
  q50/q90/q99 = 5/41/151. Base eligible rows are 51.91%/50.25%/50.47% of
  train/val/test, and 300-second replay eligibility is 41.44%/39.89%/40.39%.
  All-eligible window capacity (30 rows, stride 10) is 80,979/17,188/17,310;
  replay capacity is 59,923/12,505/12,738. These are feasibility upper bounds,
  not injected datasets or validated quotas.
- Extended report: `docs/calibration_v3_stage1.json` (read-only input; written
  under docs). It found 14,279/14,279 split coverage, 69,959 partial-field
  replay rows after the three-consecutive-pair effect gate, and 11,712 nominal
  120-second gated test episode starts. A 10,000-row in-memory abrupt-boundary
  oracle trial has gross-tier recall 0.9997; it is a generator sanity check,
  not a learned-model result.

## Models and FL
- Centralized LSTM (1 layer, hidden 64), seed 42: test accuracy 0.664533,
  macro-F1 0.648890, normal-data FPR 0.726333; best validation macro-F1
  0.652434 at epoch 9. E-001 reproduces the earlier baseline exactly.
- FL code: none yet. v2 `train_client_ids.npy` is an IID placeholder.

## Phase 0 reproduction
- Cleaned reproduction: `data/reproductions/phase0/processed/`; parquet bytes
  differ from the immutable original, but regenerated v2 train/val/test tensors,
  labels, and train client IDs are exactly equal to the immutable v2 artifacts.
- E-001 result: `results/E-001/run1/`; configuration and measured metrics are
  registered in `EXPERIMENT_REGISTRY.md`.
- Comparison: E-001 and `centralized_lstm/baseline_h64_l1_seed42` have identical
  `test_metrics.json` values and identical confusion matrices. E-001 is reproducible
  for this seed, not a multi-seed estimate.

## v2 baseline diagnostic
- Weak baseline: normal-data FPR is 72.63%; position-spoof recall is 28.37%.
- Read-only source-window diagnostic: 682/17,000 normal windows (4.01%) have
  constant finite lat/lon/velocity; 1,904/17,000 (11.20%) contain `onground=True`;
  their union is 2,451/17,000 (14.42%) effectively frozen normal windows.
- H1 (unverified causality): frozen/on-ground normal windows may contribute to the
  high normal FPR. H2 (unverified): normal/position-spoof overlap or v2 generator
  shortcuts may contribute to low position-spoof recall. The diagnostic establishes
  prevalence only; causal tests belong to the Phase 2 shortcut audit.
- Cross-check of all 1,521 normal-to-v2-freeze false positives: 24 (1.58%) had
  constant finite lat/lon/velocity, 53 (3.48%) had any `onground=True`, 77 (5.06%)
  met the effectively-frozen union, and 157 (10.32%) had any missing core feature.
  These descriptive overlaps do not support frozen/on-ground/missingness as a
  sufficient explanation for this error mode.

## Key risks / open questions
- Shortcuts (missingness, attack placement), unrealistic class balance.
- Very limited time/geographic coverage of data -> weak non-IID story unless
  more data is obtained. **Open question for the human: can more OpenSky
  hours/days/regions be downloaded?**
- D-004--D-009 are approved. Manipulation/replay are Phase 1 stage 1; ghost/DoS
  are deferred to stage 2. Track A novelty detection is primary; Track B supervised
  multiclass is an upper-bound reference on identical splits/evaluation sets.
- D-011--D-018 are proposed review amendments. D-017 records that D-015
  supersedes relevant D-012 density/tier/quota parts and D-016 supersedes
  relevant D-013 fixed-split/realization parts. D-018 proposes the current
  replay/freeze, altitude, quota, eta, and oracle requirements.

## Where things are
- Agent rules + roadmap: `AGENTS.md`, `docs/ROADMAP.md`
- Decisions: `docs/DECISIONS.md`; experiments: `docs/EXPERIMENT_REGISTRY.md`
- Attack methodology mapping: `docs/attack_generation_methodology.md`
