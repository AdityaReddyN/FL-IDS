# DECISIONS.md

Append-only log of design decisions. Number sequentially (`D-001`, ...). If a
decision is reversed, add a new entry that references the old one.

## Template

```
### D-### — Title (YYYY-MM-DD)
**Context:** why a decision was needed
**Options considered:** A, B, C
**Decision:** what we chose
**Why:** rationale
**Type:** paper-grounded | implementation choice | engineering convenience
**Consequences / risks:**
```

---

### D-001 — Attack labels are synthetic and data-layer only (2026-10-16)
**Context:** Data is OpenSky decoded state vectors; Li et al. PDF equations unavailable.
**Decision:** All attacks are data-layer simulations on decoded fields. Numeric ranges
not visible in the accessible paper text are declared implementation choices.
**Type:** implementation choice
**Consequences:** Paper must not claim full reproduction of Li et al. or operational IDS performance.

### D-002 — Split by aircraft, preprocessing fit on train only (2026-10-16)
**Decision:** Keep v2's convention: aircraft-level splits; imputer/scaler fit on train aircraft.
Extend with region-based splits for geographic experiments.
**Type:** engineering/validity

### D-003 — Context records live in `docs/` (2026-10-16)
**Context:** The project protocol specifies `docs/` as the durable project memory,
but the five context records were initially at the repository root.
**Decision:** Move `PROJECT_CONTEXT.md`, `ROADMAP.md`, `PROGRESS_LOG.md`,
`DECISIONS.md`, and `EXPERIMENT_REGISTRY.md` into `docs/` using Git.
**Why:** Aligns the repository layout with the documented context protocol.
**Type:** engineering convenience
**Consequences / risks:** Links and documentation must use the `docs/` paths.

### D-004 — Attack proportion (APPROVED; 2026-10-16)
**Context:** Li et al. Eq. 10 provides a density/strength-aware attack proportion;
the paper's 0.05% flight share is too small for this dataset.
**Options considered:** Paper's fixed 0.05% share; a fixed larger share; Eq. 10 sweep.
**Decision:** Approved: use Eq. 10 with tau swept over {0.005, 0.01, 0.05, 0.1}.
**Why:** Preserves the paper's parameterisation while providing enough examples.
**Type:** implementation choice
**Consequences / risks:** Explicit documented deviation from the paper's 0.05% share.

### D-005 — Amplitude and stealth (APPROVED; 2026-10-16)
**Context:** The paper supplies Eqs. 11-13 but not all numeric constants.
**Decision:** Approved: derive amplitudes from historical per-attribute statistics,
state the Eq. 11 interpretation, and define three stealth tiers via Gamma/zeta;
add Eq. 12 Gaussian noise.
**Why:** Uses available paper structure without inventing unspecified constants.
**Type:** implementation choice
**Consequences / risks:** Requires calibration validation.

### D-006 — Two detection tracks (APPROVED, Option C; 2026-10-16)
**Context:** The paper treats labels as evaluation-only, while the current v2 baseline is supervised.
**Decision:** Track A is the primary headline: novelty detection is trained on normal
data only in centralized and federated settings, with attack labels used only for
evaluation, following Li et al. Track B is a supervised multiclass upper-bound
reference. Both tracks use identical aircraft splits and evaluation sets.
**Why:** Better matches the paper's stated label usage.
**Type:** implementation choice
**Consequences / risks:** Expands Phase 3/5 scope; comparisons must be reported fairly.

### D-007 — Rename v2 replay label (APPROVED; 2026-10-16)
**Context:** v2 `replay_freeze_sim` is a fixed-value manipulation, not delayed replay under Eq. 8.
**Decision:** Retain v2 labels for baseline provenance but name the Phase 1 class
accurately and add true 300 s delayed replay on lat/lon/baroaltitude at minimum.
**Why:** Avoids conflating distinct paper attack families.
**Type:** paper-grounded
**Consequences / risks:** No mutation of v2 artifacts.

### D-008 — Staged ghost and DoS scope (APPROVED; 2026-10-16)
**Context:** Extracted details specify ghost and DoS variants absent from the prior accessible text.
**Decision:** Stage 1 implements manipulation and replay only. Stage 2 then implements
ghost variants and DoS period/whole/cycle variants; ghosts stay with their source
split and use reserved synthetic ICAO IDs. Audit DoS missingness shortcuts.
**Why:** The source now gives enough high-level procedure to implement transparently.
**Type:** implementation choice
**Consequences / risks:** Physical plausibility and shortcut risks remain; ghost/DoS code is deferred.

### D-009 — Episode-level injection (APPROVED; 2026-10-16)
**Context:** Paper attacks occur in attack windows within flights, while reference code also uses whole-flight attacks.
**Decision:** Support attack episodes within flights as well as whole-flight episodes.
**Why:** Preserves temporal attack structure and enables spanning future windows.
**Type:** paper-grounded
**Consequences / risks:** Requires episode provenance.

### D-010 — Frozen-window diagnostic definition (2026-10-16)
**Context:** Phase 0 needs a read-only check for stationary or on-ground normal v2 windows.
**Decision:** Count a window as constant only when all 30 source rows have finite
lat/lon/velocity and each feature has zero range. Report `onground=True` separately;
define "effectively frozen" as their union.
**Why:** Avoids silently treating missing values as stationary and preserves the two signals.
**Type:** engineering convenience
**Consequences / risks:** This is a descriptive diagnostic, not a causal test of model error.

### D-011 — Boundary-aware detectability and eligibility (PROPOSED; 2026-10-16)
**Context:** Review requires a clearer distinction between detectable attack boundaries
and within-episode signals, plus eligibility-matched controls.
**Decision:** Proposed: persist per-step onset/interior/offset labels; report boundary
and interior-only recall separately; define partial-field and full-field replay; use
one type-parameterized airborne/not-stale/observed/history eligibility predicate for
attacks and matched normal controls while retaining full-population normal FPR.
**Why:** Constant offsets and full-field replay may be unobservable to a single stream
away from their boundaries; matching controls prevents eligibility shortcuts.
**Type:** implementation choice
**Consequences / risks:** Ramped onset and control eligibility require human approval of
the draft tolerances and do not create a guarantee of detector observability.

### D-012 — Episode quota, density, and physical tier draft (PROPOSED; 2026-10-16)
**Context:** Review requires sufficient per-cell evaluation counts, explicit Eq. 10
density definitions, regional reporting, and physically interpretable tier starts.
**Decision:** Proposed: allow bounded multiple episodes per segment; keep tau-scaled
data as realistic prevalence and add a per-(type,tier,split) window-quota mode with
at least 500 test windows per cell. Define rho from time-local grid-cell aircraft
counts and rho0 by its nonzero p99; retain uniform-per-sub-airspace as a control.
Use the measured p50/p99 horizontal step changes as starting meter-scale tiers.
**Why:** Supports power, regional transparency, and calibration against observed motion.
**Type:** implementation choice
**Consequences / risks:** Values in the draft YAML require validation and approval;
quota mode is not prevalence-realistic.

### D-013 — Strict Track A and reproducibility draft (PROPOSED; 2026-10-16)
**Context:** Review requires zero-contamination novelty training and stronger provenance.
**Decision:** Proposed: Track A training windows contain zero attacked rows; choose
models with normal validation loss only and calibrate normal-only FPR. Hold-out attack
type experiments apply to Track B. Store natural keys/input fingerprints, derive
segment seeds from the global seed, require three injection realizations, and add a
contaminated Track A scenario in Phase 6.
**Why:** Prevents label leakage into the primary novelty claim and supports repeatable CIs.
**Type:** implementation choice
**Consequences / risks:** Increases computation and makes Track A/Track B objectives
intentionally different; comparisons remain on identical splits/evaluation sets.

### D-014 — Residual-gated attack eligibility and ambiguity handling (PROPOSED; 2026-10-17)
**Context:** Read-only calibration showed substantial natural position-versus-velocity/heading residuals that vary by speed band. A row-level field-preserving replay or freeze needs a measurable inconsistency, not only valid source values.
**Decision:** Proposed: use a shared airborne/non-stale/observed predicate plus same-segment kinematic-residual measurement. Partial replay additionally requires a measurable change at 300 s in speed, heading, or vertical rate and residual exceedance across consecutive interior pairs. Freeze changes lat/lon only and uses a fixed pre-onset anchor. Windows require minimum attacked rows and effect; insufficient overlap/effect is `ambiguous` and excluded from evaluation and Track A training.
**Why:** Makes detectability criteria explicit and applies the same eligibility population to attacked and matched-normal shortcut-audit windows.
**Type:** implementation choice
**Consequences / risks:** Natural residual tails are large, so proposed thresholds and episode capacity need validation before any result is reported.

### D-015 — Density-aware eta, calibrated tiers, and quota feasibility (PROPOSED; 2026-10-17)
**Context:** The previous rho0 form algebraically cancelled local density and imposed a 1/q99 scale reduction. Calibration measured rho q99=151 in 5-degree/60-second cells and available normal/replay capacity by split.
**Decision:** Proposed: eta is the candidate-start selection fraction, with `tau*log(1+theta)*clip(rho_ref/rho)` bounded by an eta cap; report requested and realized eta and row prevalence by region. Use residual-calibrated horizontal tiers of 500 m, 2,500 m, 5,500 m, and 11,000 m gross positive control; add quotas for qualifying windows, episodes, and unique aircraft, with capacity shortfall failure.
**Why:** Retains a measurable density effect, avoids silent quota underfill, and makes calibration values physical and auditable.
**Type:** implementation choice
**Consequences / risks:** This is Eq. 10-inspired, not a claimed recovery of inaccessible paper constants. Capacity is an upper bound until injection rejection is implemented.

### D-016 — Fixed splits, five realizations, and bounded data claim (PROPOSED; 2026-10-17)
**Context:** Comparisons across injection realizations need stable split membership and valid uncertainty units; the source covers two hours only.
**Decision:** Proposed: reuse `split_aircraft.json` for every realization, require five injection seeds when feasible, use aircraft-cluster bootstrap CIs, and state an explicit insufficient-realization caveat if fewer are available. State the 2017-06-05 00:00--02:00 UTC coverage limitation in design/limitations reporting.
**Why:** Prevents split variation from being confused with injection variation and avoids overclaiming temporal coverage.
**Type:** implementation choice
**Consequences / risks:** Five complete realizations may be computationally costly; no causal/generalizability claim follows from this limited source period.

### D-017 — Cross-reference: calibration revisions supersede earlier draft parts (PROPOSED; 2026-10-17)
**Context:** Extended calibration and review changed the meaning of eta, replay/freeze tiering, quota units, and realization requirements from the initial design draft.
**Decision:** Proposed cross-reference correction: D-015 supersedes the density/eta, physical-tier, and window-quota portions of D-012. D-016 supersedes the fixed-split and realization/CI portions of D-013. D-012 and D-013 remain historical records for their unaffected boundary, Track A, provenance, and general reproducibility decisions.
**Why:** Preserves append-only history while making the active proposal unambiguous.
**Type:** engineering/documentation
**Consequences / risks:** D-015/D-016 remain proposed; no superseded detail is approved merely by this cross-reference.

### D-018 — Extended-calibration replay, altitude, quota, and oracle proposal (PROPOSED; 2026-10-17)
**Context:** The extended read-only calibration is saved in `docs/calibration_v3_stage1.json`. It measured residuals by dt/speed and altitude by vertical-rate/dt, complete aircraft split coverage, replay gate capacity, window yield per episode, and an in-memory oracle boundary trial.
**Decision:** Proposed: retain 300 s as the paper-grounded replay delay; make 60/120/300 s a disabled labelled sensitivity sweep; remove replay horizontal-error tiers and use speed-band reporting; define freeze tiers by 90/120/180/300 s duration. Separate shared eligibility from attack-only effects, add maneuver-matched controls, use the five-attacked/three-effect-row window rule, and make uniform-per-sub-airspace the primary FL dataset. Set quota targets first on episodes and aircraft (test >=150 episodes and >=100 aircraft per cell); derive windows from observed episode yield. Use altitude-residual-derived shifts and screen geoaltitude residual glitches. Add an abrupt gross option and require the oracle residual detector to catch >=99% of gross boundaries.
**Why:** Error magnitude for replay/freeze is speed times delay/duration, whereas the measured residual distributions directly support effect gates, altitude handling, and a reproducible positive-control sanity check.
**Type:** implementation choice
**Consequences / risks:** These values are proposed and no attack data were generated. The gated test capacity is an upper bound before spacing/quota constraints; full-field replay has no defensible interior residual gate.

### D-019 — Decoupled ground truth, detectability strata, long episodes, and train-only calibration (PROPOSED; 2026-10-18)
**Context:** Review of draft_3 / D-014 / D-018 showed that conditioning window labels on a residual threshold conflated ontological ground truth with detectability, distorting subtle-tier evaluation and creating selection artifacts. Furthermore, with 30-row windows (stride 10) and 3-step ramps, nominal 90--300 s episodes produce zero interior-only windows. Finally, calibration thresholds must not leak validation/test data, and the oracle detector required evaluation under default ramps as well as abrupt onsets.
**Decision:** Proposed revisions superseding the effect-gate and window-rule portions of D-011, D-014, and D-018:
1. **Decouple truth from detectability:** An attacked window is defined solely by attacked-row count (>= 5 rows) and minimum effective ramp amplitude, NOT by residual exceedance. The requirement for "effect-qualified rows" is completely removed from the window labelling rule. `ambiguous` is reserved strictly for weak overlap (1--4 attacked rows) and excluded from Track A training and primary evaluation.
2. **Detectability reporting strata:** Detectability is reported via post-hoc strata, NOT used as a primary selection gate: (a) boundary windows, (b) interior windows with residual qualification, and (c) interior windows without residual qualification. Primary dataset generation uses shared eligibility only (ungated); residual-gated subsets are reported separately as a sub-analysis.
3. **Attack-specific effect quantities for strata:** Compared against speed-band p95:
   - Constant offset: onset/offset step displacement (`magnitude / 3` under default 3-step ramp).
   - Gradual deviation: per-step drift (`magnitude / (n-1)`) and cumulative offset (`magnitude`).
   - Gaussian deviation: pair residual compared to speed-band p95 (or sigma).
   - Partial replay: current-versus-source kinematic discrepancy.
   - Freeze: expected displacement `v * dt`.
4. **Long episode durations for interior evaluation:** Add long-episode configurations of 600 s (60 rows) and 900 s (90 rows) for manipulation and freeze, alongside the nominal 120 s setting. Calibration confirms 12,616 segments >= 600 s and 10,139 segments >= 900 s exist. A 600 s episode yields mean 2.50 interior-only windows (7.85 qualifying windows); 900 s yields mean 5.50 interior-only windows (10.84 qualifying). 90--300 s episodes yield 0 interior-only windows.
5. **Capacity and test reliability:** Report post-eligibility and post-gate capacity for freeze, manipulation, and replay by split and speed band. Any test speed band with under 100 unique test aircraft (specifically, the 0--50 m/s test band in replay has 27 unique aircraft for 120 s episode starts) must be marked as descriptive only.
6. **Train-only calibration thresholds:** Speed-band horizontal residual p95 thresholds and geoaltitude glitch screen (2,887.98 m) are strictly computed on TRAIN aircraft only (`data/sequences_v2/split_aircraft.json`). Train vs all-data differences are small: 0--50 m/s (+2.2 m), 50--100 m/s (+0.7 m), 100--200 m/s (-7.1 m), 200+ m/s (-8.0 m).
7. **Altitude separate treatment:** The 15+ m/s vertical-rate band exhibits a large train-vs-all baro p95 difference (373.4 m train vs 225.5 m all-data; geo 510.2 m train vs 381.0 m all-data) due to sparse samples. It is excluded from altitude effect strata or reported descriptively only. One shared altitude shift size per tier is used across both variants (`baro_only` and `baro_plus_geo`), calibrated from 0--5 m/s where baro and geo p95 are closest.
8. **Freeze feasibility & Eq. 12 noise semantics:**
   - 90 s freeze tier (9 rows with 3-step ramp has 3 interior rows) cannot yield interior-only 30-row windows; it is evaluable at boundary+interior stratum only.
   - Eq. 12 noise semantics: `x~'_i = x~_i + kappa * s`, where `s ~ N(0, per_step_noise_sigma_meters)` (25.0 m). Effective noise std is `kappa * 25.0 m` (subtle: 5.0 m, moderate: 2.5 m, blatant: 1.25 m, gross: 0.0 m).
9. **Oracle detector benchmarks:** Evaluated under both default 3-step ramp and abrupt onset on 10,000 clean pairs. Gross abrupt recall is 0.9999 (satisfies the >= 0.99 release gate); gross 3-step ramp recall is 0.9754. Clean maneuver-matched control FPR is 4.58% (manipulation/freeze) and 3.87% (replay). Freeze interior recall is 21.17% (expected displacement `v * dt` >= p95 residual).
**Why:** Maintains scientific honesty by separating physical ground truth from algorithmic detectability, prevents data leakage from validation/test splits, solves the interior-only window feasibility bottleneck, and sets rigorous reporting standards.
**Type:** implementation choice
**Consequences / risks:** Proposed only; awaiting human approval before any attack-generation code is written.

### D-020 — Stage 1 design approvals and implementation scope (APPROVED; 2026-10-20)
**Context:** Human review of the Draft 4 design, Draft 4 YAML, and D-019. The human approved the design principles listed below and authorized a foundation-only coding session (config, natural keys, fingerprints, seeding, splits, schemas, manifest). No attack operations or dataset generation were authorized.
**Decision:** APPROVED:
1. Decoupled window labelling: >= 5 attacked rows plus a numeric effective-ramp-amplitude rule; no residual qualification in the ground-truth label.
2. Detectability strata: boundary, interior-with-residual-qualification, and interior-without-residual-qualification, reported post hoc.
3. Primary dataset generated ungated on shared eligibility, with the residual-gated sub-analysis reported separately.
4. Long episode durations of 600 s and 900 s alongside the nominal 120 s.
5. Train-only calibration thresholds (speed-band p95 and geoaltitude glitch screen).
6. Descriptive-only rule for test speed bands with fewer than 100 unique aircraft.
7. Eq. 12 noise semantics: effective noise standard deviation is `kappa * 25.0 m`.
8. Separate treatment of the 15+ m/s vertical-rate band.

These approve the corresponding portions of D-019. NOT approved and still provisional: tier magnitudes, altitude shift magnitudes, and the quota cell matrix.
**Why:** Separates ontological ground truth from detectability, prevents validation/test leakage, enables interior-only window evaluation for long episodes, and prevents low-power test bands from supporting generalization claims.
**Type:** scientific design approval + scope approval
**Consequences / risks:** `configs/attack_v3_stage1.yaml` remains `status: proposed_unapproved` because provisional values are still embedded; `flids.attacks.config.require_approved` therefore refuses dataset generation. Do not report provisional tier, shift, or quota values as approved design.

### D-021 — Kinematics, eligibility, replay-source, and placement conventions (APPROVED amendments; span factors and field lists PROVISIONAL; 2026-10-20)
**Context:** Session 2 of the Stage 1 foundation. The human approved the plan with eight amendments covering speed bands, longitude wrapping, replay lookup, caller-built start masks, per-family required fields, per-request randomness, an actual-span filter, and real-data dt reporting.
**Decision:**
1. **Speed band is vectorized:** lower-inclusive/upper-exclusive bands `0_50`, `50_100`, `100_200`, `200_plus`; NaN maps to `missing`, negative velocity to `invalid`; scalar input returns a string, array input returns a string array. It never raises on an array.
2. **Longitude wrapping:** `pair_residual_m` wraps the longitude difference into `[-180, 180]` before converting to metres. The formula otherwise matches `scripts/calibrate_v3_stage1.py` lines 415--419 (north `dlat * 111_320`; east `dlon * 111_320 * cos(midlat)`; expected displacement `velocity * dt * (cos h, sin h)`).
3. **Replay source lookup:** `replay_source_offsets(times, eligible, delay_s=300, tolerance_s=5)` is pure and per segment. It finds the row nearest to `t - 300 s` over the whole segment, ties to the earlier row, and returns `-1` if the nearest row is absent, is the target or later, or is ineligible. It does not consult target-row eligibility. Times must be strictly increasing.
4. **Start masks are explicit:** `eligible_starts(segment_rows, n_rows, row_ok_mask, pair_ok_mask)` scans windows with prefix sums. The caller builds `row_ok_mask` as row eligibility plus attack-specific requirements (for replay, a valid source); no replay logic is hidden inside the scan.
5. **Provisional required fields** (`REQUIRED_FIELDS`; each entry is the union of fields to modify and fields needed to measure the effect):
   - horizontal manipulation and freeze: lat, lon, velocity, heading
   - altitude manipulation: baroaltitude, vertrate
   - altitude manipulation (baro + geo): baroaltitude, geoaltitude, vertrate
   - partial-field replay: lat, lon, baroaltitude, velocity, heading, vertrate
   - full-field replay: all seven features
   "Observed" means the value is not NaN **and** its `*_missing` flag is false. Missing velocity therefore makes lat/lon manipulation ineligible.
6. **Placement randomness:** each request `k` receives its own generator from `rng_for_request(k)`, intended to be built with `episode_rng(global_seed, icao24, segment_id, k)`. The remaining valid starts are shuffled with that generator and the first candidate satisfying overlap and gap is taken. Rejection reasons: `segment_too_short`, `no_eligible_start`, `overlap`, `gap_violation`, `max_per_segment_exceeded`. Gap failures do not consume candidates. Adding later requests never changes earlier placements.
7. **Duration and span (PROVISIONAL factors):** `n_rows = duration_seconds // 10`. Valid starts are filtered so the actual span `end_time - start_time` lies within `0.8x`--`1.25x` the requested duration. `MIN_SPAN_FACTOR=0.8` and `MAX_SPAN_FACTOR=1.25` are named implementation choices, not paper values; the real-data check reports how many starts they remove.
8. **Real-data check:** `scripts/check_eligibility_on_real_data.py` is written but not run. It reports calibration-style and strict eligibility shares, replay-source availability under both lookup conventions, 30-row stride-10 windows, flag/NaN disagreement, `|dlon| > 180` pairs, wrapped residual quantiles against train-only p95, span-filter removals for 120/600/900 s, and adjacent-pair dt quantiles.
9. **Housekeeping:** the manifest records `git_dirty` from `git status --porcelain`; segment IDs are coerced with `int()` before seeding; null `icao24` or `segment_id` raises `NaturalKeyError`.
**Why:** Makes the conventions explicit and testable before any attack values are generated; the caller-built masks and per-request RNG prevent hidden coupling between replay, placement, and later requests; wrapping prevents antimeridian pairs from producing false huge residuals.
**Type:** implementation choice + approved session amendments
**Consequences / risks:** REQUIRED_FIELDS and the 0.8/1.25 span factors are provisional and may change after the real-data check. The replay lookup deliberately differs from the earlier calibration convention (which selected the nearest row *among eligible rows*); the real-data script reports both so the difference is measured, not assumed to be zero. No attack data were generated.

### D-022 — Ramp convention and manipulation primitives (APPROVED with amendments; tier values PROVISIONAL; 2026-10-21)
**Context:** Session 3a of the Phase 1 foundation. The human approved the plan with seven amendments covering the displacement conversion, input immutability, active-row finiteness, Gaussian mean testing, separate Eq. 12 RNG streams, the cross-segment-boundary attribution, and the bearing domain.
**Decision:**
1. **Ramp multipliers (`ramps.ramp_multipliers`):** `linear_mix` uses `a_k = k/(ramp_rows+1)` for onset row `k` (0-based), so a 3-row ramp is 0.25/0.50/0.75; interior rows are 1.0; the offset is mirrored (0.75/0.50/0.25). It raises when `n_rows < 2*ramp_rows+1`. `abrupt` sets every row to 1.0, labels the first row `onset` and the last `offset` (single row: `onset`), and labels the rest `interior`. A row is an **attack row** when `a_t > 0` and an **effective row** when `a_t >= 0.5`; both are exposed as mask helpers. Window labelling itself is not implemented.
2. **Horizontal displacement convention:** for both constant and Gaussian manipulation, `north_deg = north_m / 111_320`; `new_lat = lat + north_deg`; `east_deg = east_m / (111_320 * cos(radians((lat + new_lat)/2)))`; `new_lon` is wrapped into `[-180, 180)`. This matches `kinematics.pair_residual_m` exactly and is tested by measuring displacements back through that function for bearings 0/45/90/225 at latitudes 0/40/60. Bearings are caller-supplied degrees in `[0, 360)`; values outside that range, including 360, raise rather than wrap. A resulting latitude outside `[-90, 90]` rejects the call with `reason="latitude_out_of_range"`; nothing is clipped.
3. **Manipulation primitives (`manipulation`):** `constant_horizontal` applies a scaled constant offset; `gaussian_horizontal` draws independent per-row `N(0, sigma_m**2)` north/east components and scales them by `a_t`; `eq12_noise` adds `kappa * N(0, per_step_sigma_m**2)` per component only on `a_t > 0` rows (effective std `kappa * per_step_sigma_m`); `altitude_constant` supports `baro_only` and `baro_plus_geo` with one caller-signed shift scaled by `a_t`. Altitude results outside `[-500, 20000]` m reject the call.
4. **Shared result and immutability:** every function returns a `ManipulationResult(values, multipliers, rejected, reason)`. Inputs are copied and never mutated; rows with `a_t == 0` are copied through bit-identically, including longitude values outside `[-180, 180)` and `-0.0`. On active rows, target arrays containing NaN or inf raise a clear `ValueError`. Metadata (`onground`, `contact_lag_*`, `*_missing`) is never accepted or touched.
5. **Separate RNG streams:** `manipulation_streams(episode_rng)` derives two children with `Generator.spawn(2)`. Gaussian deviation and Eq. 12 noise use their own child, so adding or removing Eq. 12 noise cannot change Gaussian draws for the same episode. With `kappa == 0`, `eq12_noise` makes no draws and returns the inputs unchanged.
6. **Provisional values** (documented as constants/docstrings only; functions never read the YAML and take explicit arguments): horizontal tier magnitudes 500/2,500/5,500/11,000 m; Gaussian sigmas 250/1,250/2,750/5,500 m; Eq. 12 kappa 0.20/0.10/0.05/0.0; per-step sigma 25 m; altitude shifts 35/125/250/500 m. These remain proposed and unapproved.
7. **Housekeeping:** placement now tracks starts pruned by overlap and reports `"overlap"` (not `"no_eligible_start"`) when earlier accepted episodes exhaust the remaining starts. `pair_valid` asserts that rows are sorted by `(icao24, segment_id, time)` and rejects null keys. `schema_fingerprint` canonicalises object/`str`/`string`/Arrow-string dtypes to `"string"` so the fingerprint is identical under pandas 2 and pandas 3, while non-string dtypes keep `str(dtype)`.
8. **Real-data attribution (read-only, NOT RUN):** `scripts/check_eligibility_on_real_data.py` now also reports, per split, fully eligible windows under segment-relative offset-mod-10, every-10th-valid-start enumeration, and global-index-mod-10 stride conventions, plus windows that may cross segment boundaries and row-mask variants (NaN-only, NaN+flags, calibration base, strict full). The output decomposes the reported train gaps (78,211 vs 80,979 base; 57,763 vs 59,923 replay) without changing or tuning any eligibility convention.
9. **Oracle correction:** the earlier oracle ramp-recall figures for constant deviation used an onset step of `magnitude/3`. Under the new `k/(ramp_rows+1)` convention the first onset step is `magnitude/4`; those ramp-recall numbers must be recomputed in Gate 1b and are not comparable to the earlier table.
**Why:** Fixes the ramp semantics and metre conversion before episode integration, makes manipulation pure and reproducible, prevents Eq. 12 noise from perturbing Gaussian draws, and gives the real-data check enough attribution to explain the reported capacity gap without tuning to it.
**Type:** implementation choice + approved session amendments
**Consequences / risks:** Tier magnitudes, Gaussian sigmas, kappa, and altitude shifts are provisional and must not be reported as approved design. The real-data attribution and the corrected ramp oracle numbers remain unmeasured until the human runs the script / Gate 1b. No replay, freeze, gradual deviation, window labelling, dataset generation, or training was implemented.

### D-023 — Displacement composition, gradual deviation, replay, freeze, and detectability helpers (APPROVED with amendments; 2026-10-21)
**Context:** Session 3b of the Phase 1 foundation. The human approved the plan with six amendments covering gradual effective-row counts, a time-limited freeze anchor, strict replay-source validation and an in-episode-source test, the `residual_series` convention, hard-coded pre-refactor reference arrays, and Stage-1 noise scope.
**Decision:**
1. **Composition (`manipulation`):** `horizontal_displacement_constant(a, magnitude_m, bearing_deg)` and `horizontal_displacement_gaussian(a, sigma_m, rng)` return metre components already scaled by `a_t`; `apply_horizontal_displacement(lat, lon, a, north_m, east_m)` performs the D-022 metre-to-degree conversion and returns `ManipulationResult`. `constant_horizontal` and `gaussian_horizontal` are thin wrappers over those pieces. Their outputs were captured as float-hex reference arrays from commit 3b64bb0 before refactoring and are asserted bit-for-bit identical in `tests/test_composition.py`.
2. **Eq. 12 noise:** `add_scaled_eq12_noise(north_m, east_m, a, kappa, per_step_sigma_m, rng)` adds `a_t * kappa * N(0, per_step_sigma_m**2)` to the displacement components **before** conversion, so the noise vanishes with the ramp and cannot create a boundary jump. The existing `eq12_noise` (unscaled, D-022) is unchanged. **Stage 1 applies Eq. 12 noise to horizontal displacement only; there is no altitude noise.**
3. **Gradual deviation:** `gradual_horizontal(lat, lon, a, magnitude_m, bearing_deg)` uses `g_i = i/(N-1)` over all `N` episode rows (`g = 1` when `N == 1`); displacement is `magnitude * g_i * a_i` along the bearing. The returned `multipliers` are the **realized** multipliers `a_i * g_i`. `ramps.effective_row_count(realized_multipliers)` counts realized values `>= 0.5`; this is the "effective row" definition for every family (constant and Gaussian have `g = 1`, so nothing changes there). With `ramp_rows=3`, `N=12` yields 4 effective rows and `N=60` yields 28. Gradual episodes need at least 5 effective rows; the **assembler (Session 3c)**, not this session, will reject shorter ones with `reason="insufficient_effective_rows"`.
4. **Replay (`replay.replay_fields`):** for each row with `a_t > 0`, `modified = (1 - a_t) * current + a_t * original[source_offsets[i]]`. Sources are always read from the **original** arrays, never from already-replayed values (tested with a 60-row episode whose sources lie inside the episode, plus a delay-10 case where sources are themselves active). Active sources must satisfy `0 <= source_offsets[i] < i`; any active `-1` rejects the whole episode with `reason="no_replay_source"` and no edge-fill; other out-of-range sources and non-finite source values of the listed fields raise `ValueError`. `fields` must be a subset of the seven allowed names. Heading blends along the shortest arc and returns `[0, 360)`; longitude blends along the shortest arc and returns `[-180, 180)` (the rounded `+180` endpoint maps to `-180`). Per-row achieved delay is `times[i] - times[source]` with `NaN` on inactive rows. `PARTIAL_REPLAY_FIELDS` is `lat, lon, baroaltitude`; `FULL_REPLAY_FIELDS` is all seven.
5. **Freeze (`freeze`):** `freeze_lat_lon` blends toward a caller-supplied anchor and changes only `lat`/`lon` (shortest-arc longitude). `anchor_from_offsets(lat, lon, eligible_mask, start_offset, times, max_anchor_age_seconds=30.0)` returns the last fully eligible (mask true and finite lat/lon) row **strictly before** `start_offset`, provided its age `times[start_offset] - times[anchor]` is at most the limit; otherwise it returns `None` and the caller must reject with `reason="no_freeze_anchor"`.
6. **Detectability (`detectability`):** `residual_series(lat, lon, velocity, heading, time)` returns one residual per adjacent pair; element `k` covers the pair `(k-1, k)`, uses the velocity and heading of row `k-1` (the earlier row), and element 0 is `NaN`, matching the calibration script. `injected_displacement_m(orig_lat, orig_lon, mod_lat, mod_lon)` returns per-row metres under the shared metre convention. These feed later reporting strata; they do not label windows.
7. **Purity and scope:** every new function copies its inputs, never mutates them, leaves `a_t == 0` rows bit-identical, and makes no file, YAML, or dataset access. No assembler, window labelling, writer, dataset generation, or training was implemented.
**Why:** Makes displacement, noise, replay, freeze, and reporting quantities explicit and testable before episode assembly, keeps the pre-refactor manipulation outputs stable, and fixes the effective-row definition for gradual deviation before the assembler depends on it.
**Type:** implementation choice + approved session amendments
**Consequences / risks:** The 5-effective-row rule is documented but not enforced yet. Tier magnitudes, sigmas, kappa, and altitude shifts remain provisional. Anchors older than 30 s or absent produce `None` rather than an exception, so the assembler must handle `"no_freeze_anchor"` in Session 3c. No attack data were generated.

### D-024 — Episode assembly, no-op guard, window labelling, and windows table (APPROVED with answers; thresholds PROVISIONAL; 2026-10-21)
**Context:** Session 3c of the Phase 1 foundation. The human approved the plan and answered the open questions from D-023: (1) an effective row is a **realized** multiplier `>= 0.5` for every family; (2) the freeze anchor-age limit is **30 s**; (3) a missing replay source is a **candidate** rejection at placement because `eligible_starts` already requires a valid source for every row of the interval, while the episode-level `"no_replay_source"` is retained only as a defensive guard that logs loudly in the builder.
**Decision:**
1. **Effective-row enforcement (`episode`):** `build_episode` always evaluates `realized >= 0.5` (with `g_i = i/(N-1)` applied for gradual deviation). Fewer than `MIN_EFFECTIVE_ROWS = 5` effective rows rejects the candidate with `reason="insufficient_effective_rows"`; a linear ramp shorter than `2 * ramp_rows + 1` is rejected the same way without raising. The 9-row linear example has exactly 7 effective rows; 12-row gradual has 4 and is rejected.
2. **Episode specification and contract:** `EpisodeSpec` is a frozen dataclass carrying `attack_family`, `tier`, `subtype`, `altitude_variant`, `onset_mode` (`linear_mix`/`abrupt`), `ramp_rows=3`, `magnitude_m`, `bearing_deg`, `sigma_m`, `kappa=0.0`, `per_step_sigma_m=25.0`, `shift_m`, `replay_delay_s=300.0`, and `replay_tolerance_s=5.0`; parameters are passed explicitly and nothing reads the YAML. `build_episode(segment_values, times, eligible_mask_for_family, replay_source_offsets_or_None, start_offset, n_rows, spec, episode_rng)` is pure and in-memory: it never writes a file, never mutates its inputs, and never returns or touches `onground`, `contact_lag_*`, or `*_missing`. The seven families are `constant_deviation`, `random_gaussian_deviation`, `gradual_deviation`, `altitude_constant_deviation`, `replay_partial_field`, `replay_full_field`, and `freeze_fixed_value`.
3. **Results and rejections:** `EpisodeResult` returns the outcome, episode-relative `values` for only the family's target fields, realized `multipliers`, ramp `positions`, per-row achieved replay `delays` (otherwise `None`), per-row `changed_fields`, per-row `horizontal_displacement_m` and `altitude_change_m`, and a summary. Every expected failure is a rejection (`accepted=False`) and never raises: `latitude_out_of_range`, `altitude_out_of_range`, `no_replay_source`, `no_freeze_anchor`, `insufficient_effective_rows`, `replay_delay_mismatch` (any active row beyond tolerance), and `no_measurable_change`. A rejected result returns copies of the original target fields, no changed fields, and zero displacement arrays. The episode-level `"no_replay_source"` logs a warning to flag a placement bug.
4. **Composition:** Gaussian episodes draw displacement from the Gaussian child of `manipulation_streams`; constant and gradual episodes use the constant displacement components. When `kappa > 0`, `add_scaled_eq12_noise` is applied to the horizontal components before conversion; gradual realizes `a_t * g_t` before composing. Freeze uses `anchor_from_offsets` with the 30 s limit; replay uses full-segment original arrays so a source may precede the episode, then checks the achieved delay and slices the episode.
5. **No-op guard (PROVISIONAL):** `NOOP_MIN_HORIZONTAL_M = 100.0`, `NOOP_MIN_ALTITUDE_M = 30.0`, evaluated over **effective** rows only. Constant, Gaussian, gradual, and freeze episodes use `detectability.injected_displacement_m`; the altitude family uses the absolute altitude change; replay counts both horizontal displacement and baroaltitude/geoaltitude change, and full-field replay accepts if any field moves the aircraft horizontally or vertically above the threshold. Below threshold rejects with `"no_measurable_change"` (e.g. a stationary freeze, an identical-source replay). These thresholds are implementation choices, not approved design.
6. **Window labelling (`windows.label_windows`):** mirrors `scripts/build_sequences_v2.py` for one segment: `window_rows=30`, `stride=10`, starts at segment-relative row 0, and only full windows (`range(0, len - window_rows + 1, stride)`). A window is `normal` when no row has `a_t > 0`; `attacked` when at least 5 rows are effective; `ambiguous` when attack rows exist but fewer than 5 are effective. Its stratum is `none` without attack rows, `boundary` if it contains an onset or offset row, and `interior_only` if it contains attack rows but no boundary row. `episode_id` is `-1` for normal windows, and a window overlapping two episodes raises `AssertionError`. Residual strata are not computed. The realized-multiplier rule applies here too.
7. **Sixth output table (`schemas`):** `windows` adds `window_id`, `icao24`, `segment_id`, `split`, `start_offset`, `n_rows`, `label`, `stratum`, `n_attack_rows`, `n_effective_rows`, `episode_id`, `attack_family`, `attack_subtype`, and `tier`, validated by the existing helpers and enumerated against `WINDOW_LABELS`/`WINDOW_STRATA`. The schema docstring now records that `attacked_rows.ramp_multiplier` and `step_labels.ramp_multiplier` hold the realized multiplier.
8. **Real-data check (read-only, NOT RUN):** `scripts/check_windows_on_real_data.py` places one 120/600/900 s `linear_mix` episode uniformly on eligible, span-filtered starts of 1,000 seeded random train segments, labels the windows in memory, and reports mean attacked, ambiguous, and interior-only windows per episode. It compares 600/900 s against the earlier calibration means (attacked 7.85/10.84; interior-only 2.50/5.50) and prints differences without tuning.
**Why:** Turns the primitives into a single deterministic episode contract, enforces the effective-row rule before any dataset exists, fixes the window truth labels and strata to the v2 anchoring convention, and gives the schema the per-window record the writer will need.
**Type:** implementation choice + approved session answers
**Consequences / risks:** The no-op thresholds are provisional and may reject weak but intentional attacks or admit barely measurable ones; they must be revisited before generation. Tier values remain provisional. Missing/older freeze anchors and insufficient effective rows are rejections rather than errors. The real-data window yields are unmeasured until the human runs the script, so comparisons to the calibration means are not yet evidence. No dataset assembler, selection logic, writer, CLI, dataset, or training was implemented.

### D-025 — Pure overlay assembler and independent parameter streams (implementation choice; 2026-10-22)
**Decision:** `parameter_rng` derives SHA-256 entropy from `global_seed|icao24|segment_id|params` and an episode-index spawn key, isolating bearing/sign draws from episode noise and placement. `assemble_overlay` is pure/in-memory and accepts only explicit `OverlaySpec` values; it never reads YAML or writes data. It preserves every source row, selects eligible segments with the first `segment_rng` draw (`u < tau`), and records the realized Bernoulli selection. It uses 5-degree cells `floor((lat+90)/d):floor((lon+180)/d)`, deterministic int63 episode IDs, placement/build rejection rows, and schema-validated seven-table output including `segments`.
**Why:** Makes selection, parameter randomness, and provenance independently reproducible before a writer or generated dataset exists.
**Consequences / risks:** Eta is a requested probability over eligible aircraft-segments; realized eta is binomial. The new real-data check is written but unrun. Tier values, thresholds, and no-op guards remain provisional; no generated data are authorized.

### D-026 — Assembler review fixes (implementation choice; 2026-10-22)
**Decision:** Replay provenance stores the global `source_row_id` of the selected source row, not its segment-relative offset. Placement has an independent SHA-256-labelled RNG stream, and `place_episodes` returns each accepted request index explicitly; this changes episode placement relative to D-025 but makes build noise independent. Provenance JSON is strict (`NaN`/infinities become `null`).
**Selection-name review:** `selection_method="uniform_per_subairspace"` is inaccurate for the implemented independent global Bernoulli aircraft-segment selection. Candidate accurate names are `bernoulli_eligible_segment` (recommended) or `global_bernoulli_segment`; no schema/value rename is made pending approval.
**Deferred metadata:** `speed_band` needs an explicit selected convention/function and episode-median velocity calculation. `freeze_anchor_source_row_id` needs `anchor_from_offsets` (or its caller) to return the anchor offset as well as coordinates. Neither is implemented here.
**Consequences / risks:** Golden stream values deliberately lock the currently supported NumPy generator behavior. Windows spanning two distinct accepted episodes remain rejected by the existing labeller; multi-episode configuration must account for window overlap.
