# Attack V3 Design — Revised Review Draft

**Status:** design/configuration review only. No attack-generation code is
authorized until the human approves this document and
`configs/attack_v3_stage1.yaml`.

## Scope and claims

V3 is a labelled, row-level **data-layer simulation** from decoded OpenSky
state vectors, not raw ADS-B messages. Labels are synthetic; no result can
establish operational aviation-IDS performance, RF/message replay fidelity, or
signal-level security. Source and v1/v2 artifacts are immutable.

Stage 1 contains manipulation and true 300-second delayed replay. Stage 2,
after separate review, may contain ghost injection and DoS (D-008).

## Output, provenance, and reproducibility

Output root: `data/attack_generation_v3/<dataset_id>/`, containing
`config.json`, `manifest.json`, plausibility report, before/after plots, and:

| Table | Granularity | Required fields |
|---|---|---|
| `attacked_rows.parquet` | every row | `row_id`, `source_row_id`, `natural_key_json`, `input_content_sha256`, `icao24`, `segment_id`, `time`, source and modified state columns, `is_attack_row`, `attack_type`, `attack_subtype`, `episode_id`, `episode_position`, `replay_source_row_id`, `replay_delay_seconds`, `attack_parameters_json` |
| `modified_row_provenance.parquet` | changed row | identifiers above; original/modified values JSON, changed features JSON, parameter set, selection method, candidate ID, validation status/reason |
| `episodes.parquet` | episode | episode/target IDs, region, start/end source IDs/times, type/subtype/tier, requested/effective delay, seed derivation, parameters, acceptance/rejection reason |
| `rejected_candidates.parquet` | attempted candidate | candidate, target, requested interval/parameters, eligibility result, rejection stage/reason |
| `step_labels.parquet` | every output row | `row_id`, `episode_id`, `is_attack_row`, `attack_type`, `attack_subtype`, `episode_position` |

The natural key is `(icao24, segment_id, time, segment_row_offset)`; it
disambiguates a source row independently of Parquet row ordering. Every output
also stores the SHA-256 content fingerprint of the cleaned input and its schema
fingerprint alongside `source_row_id`.

A global seed is required. The random stream for a segment is deterministically
derived as `SHA-256(global_seed | icao24 | segment_id)`, then episode index,
so unrelated segments do not change if another segment is rejected. At least
three independent global-seed injection realizations are required for reported
confidence intervals; manifests identify all realization IDs.

## Per-step and window labels

An attacked step receives `episode_position`:

- `onset`: first ramped or abrupt attack steps;
- `interior`: fully applied attack steps excluding boundaries;
- `offset`: final ramped or abrupt attack steps;
- `none`: normal step.

The configuration supports a ramped onset (and symmetric offset) with a linear
multiplier across a declared number of steps. A window is `boundary` if it
contains any onset/offset step; it is `interior_only` if it contains attack
steps but no boundary. Report recall separately for boundary and interior-only
windows, as well as overall recall and normal FPR.

This distinction is necessary: a single-stream detector has no general basis
to detect a constant offset away from episode boundaries. It likewise cannot
reliably detect full-field replay away from boundaries, because the replayed
stream can remain internally consistent. Such limitations must be reported,
not treated as detector failures alone.

## Stage 1 attack families and observable signals

### Manipulation

Implement constant, Gaussian random, and increased/gradual additive deviation
on observed location/altitude fields. No v2 fixed offsets are reused. Altitude
variants are distinct labels/parameters:

- `baro_only`: modify barometric altitude only;
- `baro_plus_geo`: apply the declared shift to both barometric and geographic
  altitude.

### Replay subtypes

True replay follows Li et al. Eq. 8: at current time `t`, values come from the
same aircraft and segment at `t - 300 s`, within the configured timestamp
tolerance. No edge filling is allowed.

| Subtype | Replaced fields | Detectable-in-principle signal |
|---|---|---|
| `replay_partial_field` | lat, lon, baroaltitude minimum | inconsistency between location/altitude and unmodified velocity, heading, vertical rate, or implied kinematics; boundary discontinuity |
| `replay_full_field` | all state features selected in config | primarily onset/offset discontinuity and temporal lag relative to external evidence; no reliable within-episode single-stream signal |

### Fixed-value freeze

`freeze_fixed_value` is a manipulation subtype, not replay. It retains a
separate label and provenance. A freeze is eligible only when the original
airborne stream changes over the interval; natural stationary behavior is never
given a freeze label.

## Shared eligibility and matched controls

Define one parameterized predicate `eligible_episode(type, fields, interval)`:

1. every target row is airborne (`onground != True`);
2. every target row is not stale: finite `contact_lag_seconds` within configured
   bounds;
3. all target fields are observed on every target row;
4. for replay, every target row has same-aircraft/same-segment prior history
   at the 300-second delay within configured tolerance, and the replay source
   satisfies the same airborne/not-stale/observed requirements;
5. the source trajectory has configured non-trivial motion where a replay or
   freeze needs to be distinguishable.

The predicate is applied identically to type-matched normal control windows in
the shortcut audit and matched evaluation sets. Report FPR on those matched
normal controls **and** on the full, unfiltered normal population. This keeps
eligibility filtering from hiding operationally relevant false alarms.

Injection does not alter raw missingness, `onground`, `contact_lag_seconds`,
`contact_lag_missing`, or related metadata. These are provenance/diagnostic
fields, not model inputs. A derived `is_stale` flag records its threshold and
missing-data policy. Natural on-ground/stale data are excluded from attack
eligibility but retained in the full normal population.

## Episode counts, proportion, and regions

Several non-overlapping episodes may occur in a segment, separated by the
configured buffer. Two complementary dataset modes are required:

- **density-scaled realistic prevalence:** Eq. 10 selects episodes according
  to `tau`; it is the prevalence-aware evaluation set;
- **quota mode:** iteratively fills each `(attack_type, tier, split)` cell to a
  target number of qualifying windows after windowing. The starting proposed
  minimum is **500 test windows per cell**; train/validation targets are in the
  draft YAML. The manifest prints requested and realised episode, attacked-row,
  and qualifying-window counts per cell.

For Eq. 10, partition the measured bounding box into fixed grid sub-airspaces.
At an episode start, `rho` is the unique aircraft count with any valid source
row in that grid cell during the configured symmetric time window. `rho_0` is
`min(rho / q99_nonzero_rho, 1)`, where `q99_nonzero_rho` is measured over all
eligible cell-time observations in the source dataset. The manifest stores the
calibration population and quantile. The density-scaled mode uses the paper's
form `eta = tau * rho_0 * log(1 + theta) / rho`; a uniform-per-sub-airspace
mode is a control that samples eligible episode candidates equally by grid cell.

Every episode records grid ID/bounds and region. Reports give source rows,
eligible rows, attacked rows, episodes, and realised prevalence per region.

## Starting amplitude tiers — proposed, not validated

The tier calibration is an implementation choice under D-005. On the immutable
cleaned table, airborne observed 10-second steps measured:

| Axis | p50 absolute step | p99 absolute step |
|---|---:|---:|
| latitude equivalent | 469.25 m | 4,305.97 m |
| longitude equivalent | 950.64 m | 5,371.12 m |

Starting horizontal constant/ramp end amplitudes are proposed as:

| Tier | Latitude | Longitude | Basis |
|---|---:|---:|---|
| subtle | 469 m | 951 m | 1.0 × p50 |
| moderate | 2,153 m | 2,686 m | 0.5 × p99 |
| blatant | 4,306 m | 5,371 m | 1.0 × p99 |

Signs/directions are sampled deterministically from each segment seed. Baro and
geo shifts use separately measured p99 vertical changes and remain parameterized
by the altitude variant. Gaussian noise and Gamma are recorded but do not claim
validated stealth. These are starting values to validate with plausibility,
detectability, and shortcut reports before any scientific result is reported.

## Sequence v3 and Phase 2 safeguards

Aircraft splits happen before windowing; normal/attacked copies and all episodes
from an aircraft remain in one split. Required safeguards:

1. derive delta features only within a segment; starts/gaps are undefined,
   never bridged;
2. never median-impute within a window; use train-only global preprocessing or
   explicit masks while preserving original missingness;
3. retain on-ground/stale flags as provenance and audit variables;
4. preserve separate labels and detectability criteria for replay and freeze;
5. test `contact_lag_seconds` for label leakage before it may become a feature.

The shortcut audit includes missingness-only, window-position-only,
summary-statistic-only, delta-only, on-ground/stale-only, and contact-lag-only
baselines. Failure blocks Phase 2 acceptance.

## Detection tracks and evaluation

**Track A — primary novelty track.** A training window must contain **zero
attacked rows**, including rows overlapping any episode. Train only on normal
training-aircraft windows. Choose models using normal validation reconstruction/
novelty loss only, and calibrate thresholds on declared normal validation FPR;
no attack-labelled validation set is used for Track A hyperparameters. Attack
labels are evaluation-only. Centralized and federated Track A follow identical
normal-only rules.

**Track B — supervised multiclass upper bound.** Uses the same aircraft splits
and evaluation sets as Track A but may train on synthetic labels. Held-out attack
types/tier combinations are a Track B generalization experiment; they do not
apply to Track A, which trains on no attack types.

Both tracks report balanced and realistic-prevalence evaluations, full-population
and matched-control normal FPR, per-type/tier/boundary recall, and confidence
intervals over at least three injection realizations. Phase 6 adds a
contaminated-Track-A-training scenario with a declared fraction of attack rows
to measure novelty-model robustness.

## Validation and release gate

Tests cover deterministic segment seeds, natural-key/fingerprint persistence,
no cross-aircraft/segment contamination, multiple-episode non-overlap, no edits
outside accepted episodes, replay source/delay correctness, labels/positions,
quota accounting, and rejection accounting. Reports cover geodesic steps,
implied speed, acceleration, turn/vertical rates, availability/on-ground/stale
distributions, region prevalence, and before/after trajectory plots. The plots
are required for the Stage 1 release gate.

**Requested approval:** approve this revised design and the companion draft
configuration before attack code is written.
