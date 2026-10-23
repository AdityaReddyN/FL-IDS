# PROJECT_CONTEXT.md

> **Snapshot, rewritten in place.** Keep it short and current. History belongs in
> `PROGRESS_LOG.md`. Last updated: 2026-10-23, Session 4o Phase 3 binary LSTM baseline.

## Goal
Publishable research paper on federated-learning-based intrusion detection for
ADS-B enabled systems, using OpenSky ADS-B data and synthetic attacks grounded
in Li et al. (2020), IET Information Security 14(5), doi:10.1049/iet-ifs.2018.5635.

## Current phase
Phase 1 Stage C seed-42 generation is complete and Gate 1 was accepted by the
human (D-032). The attack foundation, seven-family assembler, writer and
manifest checks are complete (D-020--D-031); Gate 0 is approved. Stage 1
parameter values were explicitly approved (D-029); the YAML remains
`status: approved`. Phase 2 sequence construction is complete. On 2026-10-23,
the human authorized proceeding past Gate 2 while retaining the E-002 shortcut
caveats (D-034). This does not mean the audit passed: per-feature summary
statistics remain informative, and E-002 is pipeline validation only. Phase 3
has begun with a binary LSTM on existing v3 windows. E-003 completed five
seeds; mean test ROC-AUC is 0.5742 (95% t CI half-width 0.0276), mean PR-AUC
0.00443, and mean normal FPR at threshold 0.5 is 0.2245. This is pipeline
validation only and does not meet the user's requested 0.9 ROC-AUC target. The
four-day `data/hdd_data` archive set has not yet been integrated or validated.

Session 4a decisions (D-028): overlay-keyed selection streams are independent;
merged datasets allow one overlay per segment and resolve conflicts by
lexicographic overlay-key order; `tau_requested` is the eligible-segment
Bernoulli probability and is explicitly distinct from paper Eq. 10 eta. Stage A
approval sheet and read-only validation are complete. Stage B now has
vectorized/whole-segment-chunk multi-overlay assembly, lexicographic conflict
resolution, a per-overlay selection-evidence table, a guarded Parquet writer,
manifest/config, descriptive plausibility report, multi-family CLI, and SVG
plot helper. D-031 corrects nullable episode IDs and records the new eight-table
output. Two seed-42 attempts were manually stopped after prolonged CPU-bound
execution; directories `stage1_seed_42/` and `stage1_seed_42_retry1/` contain
incomplete Parquet files and must not be used. A fifth seed-42 attempt,
`data/attack_generation_v3/stage1_seed_42_retry4/`, completed after adding
chunk-start/chunk-complete timings to stderr. All eight tables have valid
footers; manifest row counts, SHA-256 values, clean commit (`72958b0`), and
canonical column order/types were independently checked. The manifest records
2,970,285 attacked rows/step labels, 21,389 segments, 149,723 overlay-selection
rows, 263 accepted episodes, 63 rejected candidates, and 246,200 windows.
Accepted episodes exist for six families; gradual deviation has 48 selected
candidates, all rejected as `insufficient_effective_rows` under the approved
120-second nominal duration/five-effective-row rule. Therefore only six family
sanity plots exist. Physical plausibility is descriptive only; RF replay
fidelity, raw ADS-B bit-level effects, signal strength/receiver processing, and
multi-receiver multilateration checks are unavailable. The human accepted the
seed-42 output for Gate 1 and authorized Phase 2 (D-032), without changing the
approved parameters. Zero gradual episodes remain: all 48 selected candidates
were rejected by the approved 120-second/five-effective-row rule.

Phase 2 sequence construction is implemented in `src/flids/data/sequences_v3.py`
and `scripts/build_sequences_v3.py`. The current pipeline-validation output is
`data/sequences_v3/seed_42_phase2/` (ignored; not committed): 170,767 train,
37,712 validation, and 37,721 test windows, each with 15 channels (8 continuous
including heading sin/cos, plus 7 explicit missing flags). Aircraft splits and
truth labels are inherited from Stage C. Ambiguous windows are retained with
label -1. Preprocessing uses unique source rows from train windows only; missing
values receive train-only means and continuous channels are standardized with
train-only scales. Binary-balanced training indices match attack windows to
unique normal windows by total missing-cell count. Realistic train/validation/
test arrays remain unchanged; validation also provides a 258-window matched
audit index (129 normal + 129 attack). `onground`, contact lag, and a 30-second
stale flag are auxiliary only, not model inputs; the stale threshold is an
implementation choice. Manifest hashes for all generated arrays and metadata
were verified. Earlier random-balanced and intermediate outputs are preserved
under separate ignored paths; use only `seed_42_phase2` for current work.

E-002 is pipeline validation only. Natural validation shortcut ROC-AUCs:
missingness-only 0.4177 (training was matched), position-only 0.5076, and
per-feature summaries 0.6021. On the missingness-matched validation subset,
missingness-only was 0.5073 and summary statistics were 0.6045. Therefore
missingness is near chance in the conditioned slice and position is near chance,
but the feature-summary audit remains informative and the realistic evaluation
set retains its natural missingness imbalance. The audit did not meet its
near-chance summary-statistic criterion. Human authorization to proceed is
recorded in D-034; this is not an audit pass. Phase 3 model evaluation is
authorized, but remains pipeline validation on synthetic labels over decoded
state vectors. E-003's binary LSTM is the first trained v3 detector; its
five-seed mean test ROC-AUC is 0.5742 (95% t CI half-width 0.0276), with results
under ignored `results/E-003/`.

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
| v3 | `data/sequences_v3/seed_42_phase2/` | 30 / stride 10 | inherited aircraft 70/15/15 | normal + 7 declared attack families (gradual has 0 examples) | pipeline validation only; Gate 2 pending |

## Attacks
- v2 attacks (ad hoc, NOT from the paper): position offset (lat ±0.15, lon ±0.20),
  velocity ±80 m/s, altitude ±2500 m, freeze/replay-like. Known to be trivially
  detectable and shortcut-prone.
- v3 plan (paper-grounded, partial): constant / Gaussian / gradual deviation,
  300 s delayed replay. Ghost injection and DoS deferred. Exact equations from
  Li et al. are unavailable; numeric ranges are implementation choices.
- `docs/attack_v3_design.md` and `configs/attack_v3_stage1.yaml` are revised to Draft 4
  incorporating D-019 (superseding effect-gate and window-rule portions of D-011, D-014, D-018):
  - Ground truth decoupled from detectability: window rule requires >= 5 attacked rows +
    ramp amplitude; residual exceedance removed from window labelling.
  - Detectability reported via post-hoc strata: boundary, interior-with-residual, interior-without.
  - Primary dataset generated ungated on shared eligibility; residual-gated sub-analysis reported separately.
  - Long episode durations (600 s, 900 s) added to resolve interior-only window feasibility
    (mean 2.50 and 5.50 interior-only windows per episode; 12,616 segments >= 600 s).
  - Train-only calibration thresholds (speed-band p95, geo glitch 2,887.98 m).
  - 15+ m/s vertical-rate band treated separately due to small-sample divergence (train baro p95 373.4 m vs all 225.5 m).
  - Test speed bands with < 100 unique aircraft marked descriptive only (e.g. 0-50 m/s in replay has 27 aircraft).
  - Oracle detector benchmarked on 3-step ramp and abrupt onset (gross abrupt recall 0.9999 >= 0.99 release gate;
    gross 3-step ramp 0.9754; clean control FPR 4.58% manip/freeze, 3.87% replay).
  - Eq. 12 noise semantics clarified: effective noise std is kappa * 25.0 m.
- Extended calibration report: `docs/calibration_v3_stage1.json` (report_version 4, read-only).
- D-020 (2026-10-20) APPROVED: decoupled window labelling (>= 5 attacked rows +
  ramp amplitude), detectability strata, ungated primary dataset with gated
  sub-analysis, 600/900 s episodes, train-only thresholds, <100-aircraft
  descriptive-only rule, Eq. 12 noise semantics, and separate 15+ m/s
  vertical-rate treatment. Still provisional: tier magnitudes, altitude shifts,
  quota cell matrix.

## V3 attack foundation (implemented 2026-10-20/21)
- `src/flids/attacks/`: `config` (YAML load, required keys, approval gate),
  `keys` (natural key uniqueness and `source_row_id`), `fingerprint`
  (Parquet-metadata-independent content and schema hashes), `seeding` (SHA-256
  segment streams; `spawn_key` episode streams), `splits` (fixed aircraft split
  with disjointness/coverage checks), `schemas` (six output tables), `manifest`
  (config hash, git commit, git dirty flag, library versions, input
  fingerprints, seed).
- `kinematics` (vectorized speed bands, antimeridian-safe pair residual),
  `eligibility` (provisional per-family required fields, row/pair checks,
  prefix-sum window starts, replay-source lookup), `placement`
  (deterministic per-request RNG, max 3 episodes per segment, 600 s gap,
  0.8x--1.25x actual-span filter), `ramps` (linear-mix quarter steps and
  abrupt onset/offset conventions, attack/effective row masks, and
  `effective_row_count` on realized multipliers), and `manipulation`
  (constant/Gaussian horizontal primitives, Eq. 12 noise, altitude
  `baro_only`/`baro_plus_geo`, separate spawned RNG streams) are implemented
  per D-021/D-022.
- D-023 adds `horizontal_displacement_constant`,
  `horizontal_displacement_gaussian`, `apply_horizontal_displacement`,
  `add_scaled_eq12_noise` (Eq. 12 noise on displacement, scaled by `a_t`,
  horizontal only), and `gradual_horizontal` (`g_i = i/(N-1)`; realized
  multipliers returned). `replay` provides original-array delayed replay with
  strict sources and whole-episode `"no_replay_source"` rejection; `freeze`
  provides anchor blending plus `anchor_from_offsets` (strictly before start,
  30 s default age); `detectability` provides `residual_series` and
  `injected_displacement_m` for reporting strata.
- D-024 adds `episode` (`EpisodeSpec`, `EpisodeResult`, `build_episode` for all
  seven families with effective-row, freeze-anchor, replay-delay, and
  `no_measurable_change` rejections) and `windows` (`label_windows` with the
  v2 30/stride-10 anchoring, `normal`/`attacked`/`ambiguous` labels, and
  `none`/`boundary`/`interior_only` strata). The sixth schema table is
  `windows`. `build_episode` is pure and in-memory; its defensive
  `"no_replay_source"` rejection logs a warning because placement should have
  already excluded such candidates.
- Synthetic fixtures only: 236 tests pass. No attack episode is persisted, and
  no dataset writer, selection logic, assembler, CLI, or training exists.
  Gradual episodes need >= 5 effective rows; shorter candidates and missing
  freeze anchors are now rejected in `build_episode`.
- `scripts/check_foundation_on_real_data.py`,
  `scripts/check_eligibility_on_real_data.py`, and
  `scripts/check_windows_on_real_data.py` are written but NOT yet run. The
  windows check reports 120/600/900 s window yields per episode and compares
  them with the earlier calibration means without tuning.
- `REQUIRED_FIELDS`, the span factors (0.8/1.25), and the D-022 tier
  magnitudes/sigmas/kappa/altitude shifts are provisional.
- Replay lookup uses the nearest row overall and rejects it if ineligible; the
  calibration convention searched only eligible rows, so the real-data check
  reports both conventions.
- PyYAML pinned at 6.0.3. The `.venv` interpreter is Python 3.13.2 with pandas
  3.0.1; its default string dtype is `str`, not `object`, which the schema
  fingerprint now canonicalises.

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
- D-020 approves the D-019 design items listed above. D-011--D-018 remain
  historical proposals except where superseded. Tier magnitudes, altitude
  shifts, and the quota cell matrix are still provisional and must not be
  reported as approved design.
- D-021 fixes the eligibility/placement conventions but leaves `REQUIRED_FIELDS`
  and the 0.8/1.25 span factors provisional. D-022 fixes the ramp and
  manipulation conventions; tier magnitudes, sigmas, kappa, and altitude shifts
  remain provisional, and the ramp oracle recall must be recomputed with
  `magnitude/4` in Gate 1b. D-023 fixes composition, gradual realized
  multipliers, replay/freeze semantics, and detectability conventions; its
  5-effective-row rule and freeze-anchor rejection are enforced by D-024's
  `build_episode`. D-024 also fixes window labels/strata and adds a provisional
  no-op guard (100 m horizontal / 30 m altitude over effective rows); the guard
  thresholds are not approved design. Real-data validation of the eligibility,
  window-yield, and no-op conventions is pending the three check scripts.

## Where things are
- New-chat handoff summary: `docs/CHAT_HANDOFF.md` (navigation aid; the canonical
  session rules and current facts remain in this file and `AGENTS.md`).
- Agent rules + roadmap: `AGENTS.md`, `docs/ROADMAP.md`
- Decisions: `docs/DECISIONS.md`; experiments: `docs/EXPERIMENT_REGISTRY.md`
- Attack methodology mapping: `docs/attack_generation_methodology.md`
- Attack foundation: `src/flids/attacks/`, tests in `tests/`, real-data checks in
  `scripts/check_foundation_on_real_data.py`,
  `scripts/check_eligibility_on_real_data.py`, and
  `scripts/check_windows_on_real_data.py` (not run); the assembler real-data
  diagnostic was run once in Session 4a as pipeline validation only.
