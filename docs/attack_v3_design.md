# Attack V3 Design — Review Draft

**Status:** design-only review draft. No attack-generation code is authorized
until the human approves this document.

## Scope and claims

V3 will generate labelled, row-level data-layer simulations from **decoded
OpenSky state vectors**, not raw 112-bit ADS-B messages. Labels are synthetic;
the output cannot establish operational aviation IDS performance or RF/message
replay fidelity. The source table and all v1/v2 artifacts remain immutable.

Stage 1 implements manipulation and true delayed replay. Stage 2, after its
own review, may add ghost injection and DoS (D-008). The paper grounding is Li
et al. (2020), with exact implementation choices identified below.

## Output layout and provenance

Output root: `data/attack_generation_v3/<dataset_id>/`. The run must write a
`config.json`, `manifest.json`, rejected-candidate table, plausibility report,
and the following Parquet tables:

| Table | Granularity | Required fields |
|---|---|---|
| `attacked_rows.parquet` | every source row | `row_id`, `source_row_id`, `icao24`, `segment_id`, `time`, original state columns, modified state columns, `is_attack_row`, `attack_type`, `episode_id`, `replay_source_row_id`, `replay_delay_seconds`, `attack_parameters_json` |
| `modified_row_provenance.parquet` | modified row only | identifiers above; `original_values_json`, `modified_values_json`, `changed_features_json`, `parameter_set_id`, `selection_method`, `candidate_id`, `validation_status`, `rejection_reason` (null when accepted) |
| `episodes.parquet` | attack episode | `episode_id`, target aircraft/segment, start/end time and source row IDs, attack type, tier, requested/effective delay, target-selection fields, parameter-set ID, accepted/rejected reason |
| `rejected_candidates.parquet` | attempted candidate | candidate ID, target identifiers, requested interval/parameters, rejection stage/reason |

`source_row_id` is the immutable cleaned-table row order captured at read time;
`row_id` identifies the v3 output row. No row may copy data across aircraft or
segments. A replay row records its exact same-aircraft source row, so the delay
can be tested. All parameters and random seeds are persisted.

## Stage 1 attack families

### Manipulation

The initial variants modify observed latitude, longitude, barometric altitude,
and geographical altitude as supported by Li et al. Eq. 2 and Table 1:

- constant additive deviation;
- random Gaussian additive deviation;
- increased/gradual additive deviation, with a documented time function;
- optional later variants: non-linear, static magnification, and changeable
  deviation.

Partial-attribute modification is deliberate. A selected episode changes only
its documented fields; its unchanged fields and availability flags stay as in
the source. No fixed v2 offsets are reused.

### True delayed replay

Replay follows Li et al. Eq. 8: at target time `t`, replace selected state
attributes with values from the same aircraft and segment at approximately
`t - 300 s`. Stage 1 requires the source timestamp to meet a configured
matching tolerance and records the achieved delay; rows without a valid source
are rejected, never edge-filled. Minimum replay fields are lat/lon/baroaltitude;
the final field set is recorded in the manifest.

### Fixed-value freeze is distinct

A fixed-value sequence is a manipulation form, not replay. If implemented, it
will have a separate `freeze_fixed_value` label and provenance; it must not be
named replay. A freeze episode copies an episode anchor only after eligibility
checks establish that the underlying airborne source trajectory actually changes.

## Eligibility and detectable-in-principle definitions

Attack labels require a measurable difference from the source, not merely a
requested operation:

- **Replay:** for every accepted row, replay source identity/delay must be
  recorded; across the episode at least one selected field must differ from its
  current source value by a configured non-zero tolerance. The pre-attack
  trajectory must show non-trivial motion over the replay lag. Natural delayed,
  stationary, or on-ground observations are rejected as replay candidates.
- **Freeze:** selected fields are fixed to an episode anchor, while the source
  trajectory has non-trivial changes during the same interval. At least one
  selected field must differ from the unmodified row. Otherwise it is natural
  stasis, not an attack label.
- **Manipulation:** each accepted row must have an observed target feature and
  a non-zero recorded delta. Clipping/invalid coordinates/altitudes reject the
  candidate rather than silently truncate it.

Exact movement and matching tolerances are configuration values to be approved
with the implementation; they are not claims made by Li et al.

## Target selection, proportion, and episodes

Manipulation and replay select flights. Stage 1 supports random selection first
and designs provenance for future area and neighbour selection. Candidate
episodes have variable time duration, are contained in one segment, and can
span later sequence-window boundaries (D-009). No window-level injection occurs.

Attack proportion follows Li et al. Eq. 10. The experiment sweep uses
`tau ∈ {0.005, 0.01, 0.05, 0.1}` (D-004); `theta`, local density `rho`, and its
normaliser `rho_0` are recorded for every run. The paper's 0.05% whole-flight
share is not used because it would yield too few targets here. The manifest
reports requested and realised aircraft/row/episode proportions separately.

## Amplitude, noise, and stealth tiers

Li et al. Eq. 11 gives an ambiguous historical-statistics bound, so this is an
**implementation choice** (D-005): calculate robust per-feature, training-scope
historical statistics before injection; record the exact interpretation and
calibration population. Eq. 12 Gaussian noise uses zero mean and a configured
small scale. Eq. 13 Gamma is reported as a descriptive proxy, not a validated
operational stealth score.

Three configuration tiers will be defined before code approval:

| Tier | Intended behaviour | Parameters recorded |
|---|---|---|
| subtle | small, history-bounded changes with maximum noise share | amplitude multiplier, Gaussian sigma, kappa, realised deltas, Gamma proxy |
| moderate | middle calibrated change/noise setting | same fields |
| blatant | large but valid history-bounded changes with lower noise share | same fields |

Tier thresholds cannot be inferred from the paper; they require approval with
the implementation configuration and must be validated with plausibility
reports rather than assumed stealthy.

## Availability, on-ground, and natural-staleness controls

V3 must not make attacks easier to classify through availability:

- Injection does not create or remove missing values in Stage 1. Manipulation
  operates only on observed selected values, while normal comparison windows are
  matched/stratified by source missingness and on-ground/stale status in Phase 2.
- Retain raw missingness indicators, `onground`, `contact_lag_seconds`, and
  `contact_lag_missing` in row provenance. Add configured `is_stale` derived
  from contact lag, retaining threshold and missing-value policy in the config.
- Exclude on-ground and naturally stale rows from replay/freeze eligibility so
  natural stationary behaviour is never labelled as an attack.
- Do not use `contact_lag_seconds` as a model feature unless the Phase 2 leak
  audit demonstrates no label association attributable to construction.

## Sequence v3 and Phase 2 requirements

Aircraft splits occur before window creation and all source-derived normal and
attacked variants remain in the same split. Sequence construction must satisfy:

1. add delta features only within a segment; mark segment starts/gaps undefined
   rather than bridging them;
2. do not median-impute within windows; use train-only global preprocessing or
   explicit masks, preserving original missingness;
3. retain on-ground and stale-data flags for provenance/diagnostics;
4. maintain separate, detectable true-replay and fixed-value-freeze definitions;
5. run a `contact_lag_seconds` label-leak check before including it as a feature.

The shortcut audit additionally tests missingness-only, position-only,
summary-statistic, delta-only, on-ground/stale-only, and contact-lag-only
baselines. A failure blocks Phase 2 acceptance rather than being hidden by a
main-model score.

## Detection tracks and evaluation

**Track A — primary novelty detection.** Training uses normal rows/windows from
training aircraft only. Attack labels and generated attacks are excluded from
training. Validation threshold calibration uses held-out normal validation data
at a declared target FPR; attack-labelled validation/test data are evaluation
only. Centralized and federated Track A use the same split and normal-only
training rule. Hold out designated attack types/tier combinations from training
entirely for unseen-attack evaluation.

**Track B — supervised multiclass upper bound.** Uses the identical aircraft
splits and evaluation sets as Track A, but may train on synthetic attack labels.
It is reported as an upper bound, never as the primary headline result.

Both tracks report prevalence-aware and balanced evaluation sets, normal FPR,
per-type recall, PR-AUC/ROC-AUC where valid, and detection latency. Results are
synthetic data-layer simulation results only.

## Validation and release gate

Before implementation is accepted, tests must cover deterministic seed use,
no cross-aircraft/segment contamination, no changes outside accepted episodes,
replay source and delay correctness, label/delta correctness, and rejection
accounting. Reports must quantify plausibility (geodesic steps, implied speed,
acceleration, turn and vertical rates), missingness/on-ground/stale distributions,
and split membership.

**Requested approval:** approve this schema, the stated Stage 1 scope, and the
requirement to approve concrete tolerance/tier configuration before attack code
is written.
