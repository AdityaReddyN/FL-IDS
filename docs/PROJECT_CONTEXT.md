# PROJECT_CONTEXT.md

> **Snapshot, rewritten in place.** Keep it short and current. History belongs in
> `PROGRESS_LOG.md`. Last updated: *(agent: set date + session on every update)*

## Goal
Publishable research paper on federated-learning-based intrusion detection for
ADS-B enabled systems, using OpenSky ADS-B data and synthetic attacks grounded
in Li et al. (2020), IET Information Security 14(5), doi:10.1049/iet-ifs.2018.5635.

## Current phase
Phase 0 (see `ROADMAP.md`). Status: complete; Gate 0 human approval pending.

## Data (VERIFY AND FILL IN during Phase 0 — values below are unverified)
- Source: OpenSky Network **decoded state vectors** (not raw 112-bit messages), ~10 s sampling.
- Raw files: `data/raw/*.csv` (believed to be two hourly files) — confirm count, date, time range.
- Cleaned table: `data/processed/opensky_clean_v1.parquet`
  - reproduction measured: 2,970,285 rows; 14,279 aircraft; 21,389 segments.
  - time range: 2017-06-05 00:00:00--01:59:50 UTC; lat [-39.502227, 65.120389], lon [-155.835677, 175.842876].
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

## Key risks / open questions
- Shortcuts (missingness, attack placement), unrealistic class balance.
- Very limited time/geographic coverage of data -> weak non-IID story unless
  more data is obtained. **Open question for the human: can more OpenSky
  hours/days/regions be downloaded?**
- The local Li et al. PDF and extracted details are available. D-004--D-009 are proposed and unapproved.

## Where things are
- Agent rules + roadmap: `AGENTS.md`, `docs/ROADMAP.md`
- Decisions: `docs/DECISIONS.md`; experiments: `docs/EXPERIMENT_REGISTRY.md`
- Attack methodology mapping: `docs/attack_generation_methodology.md`
