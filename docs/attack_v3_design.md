# Attack V3 Design — Extended-Calibration Review Draft

**Status:** review only. No attack-generation code is authorized until this document and `configs/attack_v3_stage1.yaml` are approved.

## Scope, provenance, and limitation

V3 is a labelled row-level **data-layer simulation** of decoded OpenSky state vectors, not raw ADS-B messages. Labels are synthetic and cannot establish operational aviation-IDS performance, RF/message replay fidelity, or signal security. Stage 1 is manipulation and delayed replay; ghost injection and DoS remain Stage 2 (D-008). The data covers only 2017-06-05 00:00:00--01:59:50 UTC.

The future output will retain source/modified values, `source_row_id`, natural key `(icao24, segment_id, time, segment_row_offset)`, input content/schema fingerprints, labels, parameters, replay provenance, region, and acceptance/rejection reasons. It will include rows, episodes, provenance, rejections, and step labels. No such output exists yet.

Reuse `data/sequences_v2/split_aircraft.json` for every realization. Extended calibration confirmed coverage of all 14,279 cleaned aircraft, with no extra or missing split IDs. Derive segment random streams from `SHA-256(global_seed | icao24 | segment_id)`, then episode index. Require five injection seeds when feasible; otherwise disclose the CI caveat. Bootstrap by aircraft, never rows/windows.

## Labels and one effective-window rule

Rows are `none`, `onset`, `interior`, or `offset`. Report boundary-window and interior-only recall separately. An attacked evaluation window is defined by one rule: it has at least 5 attacked rows **and** at least 3 effect-qualified rows. An overlapped window that fails this rule is `ambiguous` and is excluded from supervised evaluation and Track A training. This replaces the prior imprecise “tier target or residual” rule.

Effect qualification is attack-specific but always uses interior eligible pairs. Retained-kinematics horizontal attacks use post-attack horizontal residual at least the speed-band p95; altitude attacks use post-attack altitude residual at least the vertical-rate-band p95; full-field replay uses a valid 300-second source mapping because no honest single-stream interior residual criterion exists. Full-field replay results must remain boundary/interior stratified.

Single-stream detectors have no general basis to detect a constant offset or full-field replay away from a boundary. This is a study limitation, not a model-failure claim.

## Eligibility versus effect conditions

Eligibility applies identically to attacks and matched normal controls. Each target row and required adjacent pair must be airborne, have finite `contact_lag_seconds` in [0, 30], have required fields observed, remain in one segment, and have `0 < dt <= 30 s`. Replay additionally needs an eligible same-aircraft/same-segment source at t-300 s within 5 s. Controls are maneuver-matched: speed and absolute vertical-rate bands, and replay source-current maneuver-change category are matched.

Effect conditions apply to attacks only. Partial-field replay requires current/source difference of at least 1 m/s speed, 1 degree heading, or 0.5 m/s vertical rate, plus three consecutive interior pairs exceeding the speed-band p95 hypothetical partial-replay residual. Retained-kinematics manipulation/freeze requires three such interior pairs. Full-field replay has no interior residual gate; report it as eligibility-only, separately from the gated partial-field subset. This is the required gated/ungated replay comparison.

Injection never changes `onground`, missingness, `contact_lag_seconds`, or related metadata. They are provenance/audit fields, not model inputs.

## Replay and freeze

The only paper-grounded replay setting is a 300-second same-aircraft delay. Replay has no horizontal-error tiers: source/current position error is mainly speed times 300 seconds, rather than a controlled stealth magnitude. Report replay by speed band. An optional labelled 60/120/300-second delay sweep is disabled by default; it is a sensitivity analysis and cannot replace the 300-second headline setting.

Partial-field replay changes lat/lon and optional barometric altitude while retaining velocity, heading, and vertical rate. Full-field replay changes the configured complete state and is evaluated by boundary/interior strata. Onset uses linear `x'=(1-a)x_current+a*x_replay`; offset reverses it, with circular heading interpolation on the shortest arc.

Freeze changes **lat/lon only**. Its anchor is the last fully eligible position before onset and remains fixed; velocity, heading, vertical rate, altitude, and metadata remain unchanged. Freeze tiers are durations: 90, 120, 180, and 300 s. Error-based freeze/replay tiers are infeasible because error is driven by natural speed times the chosen duration, not independently controlled amplitude. Freeze uses the same linear onset/offset mix toward/from anchor.

## Manipulation, Gaussian deviation, and altitude

Horizontal constant/gradual deviations use one metre magnitude and a deterministic random bearing, converted to lat/lon at target latitude. The gradual interior multiplier is `j/(n-1)` (or 1 for `n=1`). Gaussian random deviation has its own explicit per-tier standard deviation in metres; it is not derived from kappa. Kappa is reserved for the separately declared Eq. 12 noise factor.

Altitude residual is `abs((alt_i-alt_(i-1))-vertical_rate_i*dt)`. Calibration uses vertical-rate bands. For normal low/mid vertical-rate data, geo-altitude residual p95 is approximately 33/127 m and p99 is 482/426 m for 0--5/5--15 m/s. Thus baro-only starting shifts are 25/100/200/500 m and shared `baro_plus_geo` starting shifts are 35/150/500/1,000 m (subtle/moderate/blatant/gross). These are proposed implementation values, not physical-stealth claims.

Leave `geoaltitude` untouched when its source pair has residual above the calibration global q99.9 screen of 2,880.360 m; exclude that row and its adjacent pair from `baro_plus_geo` eligibility without imputing/repairing it. Calibration found 1,494 such pairs. `baro_only` does not modify geoaltitude.

## Eta, regions, and quotas

Eta is the fraction/probability of **eligible aircraft-segments** targeted; episodes are then placed within selected segments. It is distinct from row prevalence. The optional density-scaled sensitivity mode is `eta_requested(s)=min(eta_cap, tau*log(1+theta)*clip(rho_ref/rho(s),m_min,m_max))`, where rho(s) is unique aircraft in s’s 5-degree/60-second cell and rho_ref is a single median nonzero calibration value. This removes the earlier rho/q99 cancellation. For every tau, report requested segment eta, realized targeted-segment eta, and requested versus realized attacked-row prevalence globally/by region.

**Uniform-per-sub-airspace is the primary FL dataset mode.** It samples eligible aircraft-segments uniformly by cell and uses tau as requested segment share. Density-scaled mode is secondary sensitivity/prevalence data. Every episode records region and reports region prevalence.

Quota mode sets episodes and unique aircraft first, per `(type, subtype_or_variant, tier, split)` cell: train 300/200, validation 150/100, and test **at least 150/100**. Windows are derived, not independently forced. With 30-row windows, stride 10, and the 5-row rule, a 50,000-start sample estimates 3.248 evaluable windows per nominal 120-second replay episode; 150 test episodes therefore imply about 487 qualifying windows. Freeze means are 2.861/3.156/3.756/4.953 windows per evaluable 90/120/180/300-second episode. Manifest output must include requested, feasible, and realized episodes/aircraft/windows for every cell; shortfall fails unless explicitly waived.

Residual-gated partial replay has an upper-bound 11,712 nominal 120-second test starts, with 27/233/354/196 unique aircraft for 0--50/50--100/100--200/200+ m/s starts. This does not prove every cell can meet quota after spacing.

## Tracks, oracle check, and release gate

Track A novelty training uses only zero-attacked-row, non-ambiguous windows; selection uses normal validation loss and thresholding normal validation FPR. Track B is the supervised multiclass upper bound on identical splits/evaluation sets. Held-out attack types apply only to Track B. Phase 6 adds a declared contaminated Track A scenario.

The release gate requires an oracle detector using speed-band p95 residual. The read-only 10,000-row abrupt-boundary trial obtained recall 0.0891/0.6284/0.9994/0.9997 for 500/2,500/5,500/11,000-m manipulation tiers. Require gross abrupt-boundary recall >=0.99 before release; this is a generator sanity check, not a model result. Also require isolation/delay/label/spacing tests, plausibility/capacity reports, eta/prevalence accounting, aircraft-cluster CIs, and before/after plots.

**Requested approval:** approve this extended-calibration design and YAML before any attack-generation code is written.
