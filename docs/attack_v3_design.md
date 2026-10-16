# Attack V3 Design — Calibration Revision Draft

**Status:** design/configuration review only. No attack-generation code is authorized until human approval of this document and `configs/attack_v3_stage1.yaml`.

## Scope and provenance

V3 is a labelled, row-level **data-layer simulation** from decoded OpenSky state vectors, not raw ADS-B messages. Labels are synthetic; no result establishes operational IDS performance, RF/message replay fidelity, or signal-level security. Stage 1 is manipulation and 300-second delayed replay. Stage 2 may add ghost injection and DoS only after separate review (D-008). The source covers only 2017-06-05 00:00:00--01:59:50 UTC; this two-hour interval is a material limitation.

The output root will be `data/attack_generation_v3/<dataset_id>/`, with `config.json`, `manifest.json`, plausibility report, before/after trajectory plots, and row/episode/rejection/step-label tables. Every output row retains `source_row_id`, `(icao24, segment_id, time, segment_row_offset)` natural key, cleaned-input SHA-256 content fingerprint, schema fingerprint, original and modified state, labels, parameters, and replay provenance. Episodes record their grid region, requested/effective amplitude, seed derivation, and acceptance/rejection reason.

Reuse `data/sequences_v2/split_aircraft.json` unchanged for all realizations. Segment randomness derives from `SHA-256(global_seed | icao24 | segment_id)` then episode index. Produce five independent global-seed injection realizations if capacity permits. If fewer are produced, all confidence intervals must state the insufficient-realization caveat. Use aircraft-level cluster bootstrap, never independent row/window bootstrap.

## Labels and evaluation population

Each attacked row is labelled `onset`, `interior`, or `offset`; normal rows are `none`. A boundary window has at least one onset/offset row, and an interior-only window has attacked rows but no boundary. Report recall separately for boundary and interior-only windows as well as overall recall and normal FPR.

A window is an attack window only if it has at least the configured attacked-row count and reaches the configured effective amplitude or residual over the declared interval. A window with attack overlap that fails either condition is `ambiguous`; exclude it from supervised evaluation and Track A training, and report its count/reason. Single-stream detectors have no general basis to detect a constant offset or full-field replay away from boundaries; report that limitation explicitly.

## Eligibility and kinematic detectability

For adjacent same-segment rows, let observed horizontal displacement be `d_i`, expected displacement be `e_i = v_i dt_i (cos(h_i), sin(h_i))`, and kinematic residual be `r_i = ||d_i - e_i||`. Measure it only where `0 < dt <= 30 s`, position/velocity/heading are observed, and both rows are airborne and non-stale.

One type-parameterized predicate applies identically to attack candidates, matched normal controls, and the shortcut audit: every target row is airborne, has finite `contact_lag_seconds` in [0, 30], and has target fields observed; each residual pair is measurable. Replay also requires same-aircraft/same-segment eligible source rows at t-300 s within 5 s. Partial-field replay further requires current versus replay-source difference in velocity >=1 m/s, heading >=1 degree, or vertical rate >=0.5 m/s, plus the configured residual exceedance for the required consecutive interior pairs. Freeze/replay must meet effective-amplitude/residual rules across the complete interior, not one row. Report FPR both on matched eligible normal controls and on the full unfiltered normal population.

Injection never changes missingness, `onground`, `contact_lag_seconds`, `contact_lag_missing`, or related metadata; they are provenance/audit values and not model inputs.

## Attack families and exact parameter semantics

Manipulation includes constant, Gaussian random, and gradual additive deviation. Horizontal attacks use one metre magnitude and a deterministic random bearing, converted to lat/lon at target latitude. `baro_only` modifies barometric altitude only. `baro_plus_geo` applies one shared signed metre shift to both altitude fields.

| Subtype | Modified fields | Observable signal |
|---|---|---|
| `replay_partial_field` | lat/lon and optional baro altitude | position residual versus retained velocity/heading and/or vertical-rate inconsistency, plus boundaries |
| `replay_full_field` | configured complete state | onset/offset and external evidence; no guaranteed interior single-stream signal |
| `freeze_fixed_value` | **lat/lon only** | residual versus retained velocity/heading, growing anchor displacement, and boundaries |

Freeze is not replay. Its anchor is the last fully eligible lat/lon before onset and remains fixed. It never changes velocity, heading, vertical rate, altitude, or metadata. Replay tier means its achieved current-versus-replayed horizontal error/residual band at full-mix interior; delay remains 300 s. Freeze tier means its achieved anchor-error/residual band across interior. Candidate selection rejects intervals that do not reach their assigned band.

On replay onset, use `x'=(1-a)x_current+a*x_replay`; on offset reverse the mixing. Interpolate heading on the shortest angular arc. Freeze uses that mixing only for lat/lon toward/from its anchor. Thus `a=0` outside and `a=1` on interior rows. For gradual deviation, interior index `j` among `n` has `g(j)=j/(n-1)` (or 1 if n=1); onset/offset mixing applies outside interior. Gaussian random deviation has independent zero-mean noise with `sigma_deviation=kappa*tier_horizontal_magnitude`; optional per-step noise uses its separately configured `sigma_noise_meters`.

## Density, prevalence, quotas, and capacity

The calibration uses 5-degree cells and non-overlapping 60-second cell-time windows. `rho(c)` is unique aircraft in candidate c's cell/window. `rho_ref` is the median nonzero rho over the declared eligible-candidate calibration population, calculated once for the dataset.

The following Eq. 10-inspired operationalization is an implementation choice, not recovery of an inaccessible paper constant:

`m(c) = clip(rho_ref / rho(c), m_min, m_max)`

`eta_requested(c) = min(eta_cap, tau * log(1 + theta) * m(c))`

`eta` is the selection probability/fraction of **eligible episode-start candidates** in that cell-time stratum before spacing/detectability rejection; it is not a row fraction. This retains inverse density dependence without the previous rho/q99 cancellation or a global 1/q99 reduction. Manifest/reporting must give requested eta mean/min/max, accepted episodes divided by eligible starts (realized eta), and attacked rows divided by eligible rows, globally and by region. Uniform-per-sub-airspace sampling is the control.

Several non-overlapping episodes may appear in a segment. Realistic-prevalence mode uses the approved tau sweep. Quota mode fills every `(type, subtype_or_variant, tier, split)` cell to qualifying-window, episode, and unique-aircraft targets. It prints requested, capacity, and realized counts per cell and fails rather than silently underfilling unless a human accepts the capacity exception. Capacity is an upper bound: it does not promise that amplitude, spacing, or cell quotas are feasible.

## Calibration-based proposed tiers

Read-only calibration found high-speed (>=200 m/s) residual p50/p95/p99 = 116.47/2,513.34/5,522.31 m. Tier checks are speed-band-specific; these are physical starting values, not validated stealth claims.

| Tier | Horizontal magnitude / residual target | Shared baro+geo shift | Role |
|---|---:|---:|---|
| subtle | 500 m | 50 m | near natural residual scale |
| moderate | 2,500 m | 100 m | about high-speed p95 |
| blatant | 5,500 m | 250 m | about high-speed p99 |
| gross positive control | 11,000 m | 500 m | sensitivity check, not stealth |

`geoaltitude` has vertical-step q99 47.244 m/s and maximum 3,364.992 m/s; it cannot be treated as a clean physical bound.

## Phase 2 safeguards and detection tracks

Aircraft splitting precedes windowing. Phase 2 must derive deltas only within segments, never median-impute inside a window, retain on-ground/stale flags for audit, preserve replay/freeze detectability definitions, and audit `contact_lag_seconds` and similar metadata for leakage before use. Shortcut audits include missingness, window position, summary statistics, deltas, on-ground/stale, and contact lag.

**Track A** is primary novelty detection: training windows contain zero attacked rows (including overlap) and no ambiguous windows; model selection uses normal validation loss only and thresholding uses normal validation FPR only. **Track B** is the supervised multiclass upper bound on the identical splits/evaluation sets; held-out attack types apply only to Track B. Phase 6 adds a declared contaminated-Track-A-training scenario.

The Stage 1 release gate requires tests for deterministic seeds, provenance, isolation, spacing, edits only inside episodes, replay delay/labels, quota/rejection accounting; plausibility/availability/region/capacity reports; requested-versus-realized eta; cluster CIs; and before/after plots.

**Requested approval:** approve this calibration revision and YAML before any attack-generation code is written.
