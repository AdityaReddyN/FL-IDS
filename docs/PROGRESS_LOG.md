# PROGRESS_LOG.md

Append-only. Newest entry at the BOTTOM. Never edit old entries; add a correction
entry instead. One entry per working session.

## Entry template

```
### YYYY-MM-DD — Session N — <agent name> — Phase X
**Goal:** what this session set out to do
**Done:** concrete changes (files, functions, commits)
**Ran / verified:** commands executed and their outcomes (paste key output lines)
**NOT verified:** anything untested or assumed
**Results:** numbers, with pointer to result files / E-### IDs
**Problems / surprises:**
**Decisions made:** D-### references
**Next steps:** the exact next 3 actions for the next session
**Questions for human:**
```

---

### 2026-10-16 — Session 0 — handoff (human + Claude review)
**Goal:** Review repo and create agent instructions.
**Done:** Repo reviewed (read-only). Created AGENTS.md and docs/ templates.
**Ran / verified:** Code read only; no data or results available to the reviewer
(`data/` and `results/` are gitignored). No scripts were executed.
**NOT verified:** All data statistics, all model results.
**Next steps:** Start Phase 0 per ROADMAP.md.
**Questions for human:** Can more/longer/multi-region OpenSky data be obtained?
Can the Li et al. (2020) PDF be supplied?

### 2026-10-16 — Session 1 — Codex — Phase 0
**Goal:** Start Phase 0, relocate context records, and reproduce the v2 baseline.
**Done:** Moved the five context records into `docs/`; added requirements, README,
pytest skeleton, safe reproduction builder, and legacy v1 script locations. Read
`docs/li2020_extracted_details.md`; logged D-003 and D-004--D-009 (proposed/unapproved).
**Ran / verified:** `pytest` passed (1 test). Clean-table reproduction completed:
2,970,285 rows, 14,279 aircraft, 21,389 segments. Validator reported the two-hour
UTC time range and missingness in PROJECT_CONTEXT.
**NOT verified:** Complete v2 regeneration and E-001 test metrics.
**Results:** E-001 failed operationally: direct training was terminated after epoch 8,
before test evaluation; result directory contains no metrics. The v2 builder was also
terminated during reservoir sampling, after only preprocessing parameters were written.
**Problems / surprises:** The desktop command runner kills calls around 60 seconds and
also terminates background child processes, preventing the requested time-boxed runs.
**Decisions made:** D-003; D-004--D-009 proposed only.
**Next steps:** Run E-001 in a persistent terminal; run v2 regeneration there with a
defined timeout; update the registry from generated result files.
**Questions for human:** May I use a persistent local terminal/session for these runs,
or should you run the documented commands and provide the result paths?

### 2026-10-16 — Session 2 — Codex — Phase 0
**Goal:** Complete the interrupted v2 regeneration and E-001 reproduction.
**Done:** Verified the user's persistent-terminal outputs; updated E-001 and the
Phase 0 snapshot/roadmap to reflect completion pending Gate 0.
**Ran / verified:** `validate_sequences_v2.py --root data/reproductions/phase0/sequences_v2_seed42`
passed: 60,000/10,000/15,000 examples; binary missingness; disjoint aircraft
splits; valid IID client assignment. User-provided tensor comparison reports
exact equality of all v2 X/y arrays and client IDs with immutable v2.
**NOT verified:** Reproduced cleaned parquet's logical row-level equality; its
file hash differs from the immutable parquet due to serialization. Phase 1 work
has not started.
**Results:** E-001/run1 test accuracy 0.664533, macro-F1 0.648890, normal FPR
0.726333, matching the prior baseline exactly; best validation macro-F1 0.652434
at epoch 9.
**Problems / surprises:** The earlier command-runner interruption was bypassed
by the user's persistent terminal. The result is not >0.99 F1, but its high FPR
and known v2 shortcuts remain material limitations.
**Decisions made:** None; D-004--D-009 remain proposed and unapproved.
**Next steps:** Human reviews Gate 0; record approval; only then design Phase 1.
**Questions for human:** Do you approve Gate 0 and authorize Phase 1 planning?

### 2026-10-16 — Session 3 — Codex — Phase 0
**Goal:** Finalise E-001 records and diagnose frozen/on-ground normal v2 windows.
**Done:** Confirmed E-001 from `results/E-001/run1/test_metrics.json`; added
`scripts/diagnose_v2_normal_windows.py`, a read-only source-window diagnostic.
**Ran / verified:** `validate_sequences_v2.py` already passed for the reproduced
v2 directory. The diagnostic ran separately on train/val/test source windows.
**NOT verified:** Frozen/on-ground prevalence is not a causal explanation for
the classifier metrics. Parquet logical equality remains unverified; v2 arrays,
labels, and client IDs are equal as reported by the reproduction comparison.
**Results:** E-001 is done: accuracy 0.664533, macro-F1 0.648890, clean FPR
0.726333, best epoch 9. Metrics and confusion matrix exactly match the prior
baseline. Normal windows: constant 682/17,000 (4.01%), any onground 1,904/17,000
(11.20%), effectively frozen union 2,451/17,000 (14.42%).
**Problems / surprises:** The command runner required split-wise diagnostic runs;
the result totals combine the three completed split outputs.
**Decisions made:** D-010.
**Next steps:** Human reviews Gate 0; record explicit approval; begin no Phase 1
work unless approval is granted.
**Questions for human:** Do you approve Gate 0?

### 2026-10-16 — Session 4 — Codex — Gate 0 / Phase 1 design
**Goal:** Apply requested Phase 0 corrections, record Gate 0 approval, and create
only the Phase 1 v3 attack design for review.
**Done:** Corrected E-001 provenance; approved D-004--D-009, with D-006 Track A
novelty primary/Track B upper bound and D-008 staged. Added read-only comparison,
scale, normal-window, and false-positive diagnostic scripts. Created the v3 design
document; no attack-generation code was added.
**Ran / verified:** E-001 and prior prediction CSV SHA-256 both equal
`16F1660F45C37FFF7CEF6CFBB9AA5671430F1ADA3638F546F6D88850F332430D`.
Cross-check of 1,521 normal-to-freeze false positives: frozen union 77 (5.06%),
on-ground 53 (3.48%), any core missingness 157 (10.32%).
**NOT verified:** The Python version of the original E-001 training process is
not stored in its config. False-positive overlaps are descriptive, not causal.
No Phase 1 attack code, v3 data, or v3 experiment has run.
**Results:** Gate 0 approved by the human. Phase 1 is limited to design review
until `docs/attack_v3_design.md` receives explicit approval.
**Problems / surprises:** None.
**Decisions made:** D-004--D-009 approved; D-010 retained.
**Next steps:** Human reviews attack_v3_design; record approval or requested
changes; only then implement Stage 1 manipulation/replay.
**Questions for human:** Do you approve the v3 design draft and its stated
configuration-review requirement before attack code?

### 2026-10-16 — Session 5 — Codex — Phase 1 design revision
**Goal:** Revise the approved design structure and draft the requested Stage 1
configuration without writing attack code.
**Done:** Rewrote `attack_v3_design.md` to cover boundary labels/recall, replay
subtypes, shared eligibility, quotas, density regions, meter-scale tiers, altitude
variants, strict Track A, and reproducibility. Added proposed config draft.
**Ran / verified:** Measured airborne observed 10-second source steps: lat p50/p99
469.25/4,305.97 m; lon p50/p99 950.64/5,371.12 m; baro p99 182.88 m; geo p99
457.20 m. No data or result artifact was changed.
**NOT verified:** All new thresholds, grid size, quotas, and tier values are proposed
starting values only. No YAML parser is installed in the current runtime, so the
draft's syntax was manually reviewed but not parser-validated. No attack-generation,
sequence-v3, or model code was written.
**Results:** No experiment run.
**Problems / surprises:** None.
**Decisions made:** D-011--D-013 proposed.
**Next steps:** Human reviews revised design/config; record approval or revisions;
only then implement Stage 1 attack-generation code.
**Questions for human:** Do you approve the revised design and YAML draft?

### 2026-10-17 — Session 6 — Codex — Phase 1 calibration revision
**Goal:** Run the requested read-only Stage 1 calibration and revise only the attack design/YAML; do not write attack-generation code.
**Done:** Added `scripts/calibrate_v3_stage1.py`, revised `docs/attack_v3_design.md` and `configs/attack_v3_stage1.yaml`, and logged proposed D-014--D-016. No attack code, data, or result artifact was written.
**Ran / verified:** The calibration read immutable `opensky_clean_v1.parquet` and `split_aircraft.json`. It reported 260 occupied 5-degree cells; rho (60-second cells) q50/q90/q99=5/41/151; base eligible row yields 51.91%/50.25%/50.47% and replay yields 41.44%/39.89%/40.39% for train/val/test. All-eligible/replay upper-bound 30-row-stride-10 capacities are 80,979/59,923 train, 17,188/12,505 val, and 17,310/12,738 test. It found 1,083,575/1,219,040 replay candidates with at least one measurable current-versus-300-s change. Geoaltitude vertical-step q99=47.244 m/s, q999=101.346 m/s, max=3,364.992 m/s; 1,521 steps exceed 100 m/s.
**NOT verified:** Proposed residual thresholds, quotas, tier magnitudes, eta parameters, and five-realization feasibility have not been tested by injection; the capacity figures are upper bounds. Full per-cell counts are produced by `--grid-detail` but were not committed as generated data. No YAML parser was available for parser validation; the draft was manually inspected.
**Results:** No experiment run. The revised design defines eta as a candidate-start fraction and makes density matter through bounded rho-reference/rho scaling; it specifies residual-gated replay/freeze, a gross positive-control tier, ambiguous windows, fixed aircraft splits, and cluster bootstrap.
**Problems / surprises:** The original exact sliding-window density calculation exceeded the interactive runner's time limit. It was replaced with the documented fixed 60-second cell-time definition, which completes read-only and matches the revised design.
**Decisions made:** D-014--D-016 proposed only.
**Next steps:** Human reviews the calibration revision and YAML. Do not write attack-generation code until approval.
**Questions for human:** Do you approve this calibration revision and config draft for Phase 1 implementation?

### 2026-10-17 — Session 7 — Codex — Phase 1 extended calibration
**Goal:** Revise the design/YAML without attack code and save the requested extended read-only calibration JSON.
**Done:** Reworked `scripts/calibrate_v3_stage1.py` as a read-only diagnostic; wrote `docs/calibration_v3_stage1.json`; revised the design/YAML; and appended proposed D-017--D-018, including the requested D-015/D-016 supersession cross-reference.
**Ran / verified:** The diagnostic read only immutable cleaned data and the fixed split, then wrote its JSON report under `docs/`. Split coverage is 14,279/14,279 aircraft. Replay eligibility is 1,219,040 rows; partial-field replay after the three-consecutive residual/maneuver gate is 69,959 rows. Gated nominal 120-second test starts by speed band are 633/2,983/5,397/2,699 (0--50/50--100/100--200/200+ m/s). A 50,000-start sample estimates 3.248 evaluable windows per 120-second replay episode. The in-memory 10,000-row abrupt-boundary oracle gives gross-tier recall 0.9997.
**NOT verified:** No episode placement, spacing, quota fulfillment, attack labels, attack data, model, or detector was run. Capacity is an upper bound. The oracle is a deterministic residual threshold, not a learned IDS. Proposed YAML values have not been approved or parser-validated.
**Results:** Replay is now fixed at paper-grounded 300 s in the headline design; freeze tiers are durations; Gaussian deviation uses independent metre sigmas; eta targets aircraft-segments; uniform-per-sub-airspace is primary for FL; altitude shifts derive from altitude residuals with a geoaltitude glitch screen.
**Problems / surprises:** The initially selected bundled Python lacked a Parquet engine; the repository `.venv` has pinned PyArrow and completed the read-only run. No dependency was changed.
**Decisions made:** D-017--D-018 proposed only; D-015/D-016 cross-reference the superseded D-012/D-013 draft portions.
**Next steps:** Human reviews the extended design, draft YAML, and calibration JSON. Do not write attack-generation code until approval.
**Questions for human:** Do you approve the extended-calibration design/configuration for Phase 1 implementation?

### 2026-10-18 — Session 8 — Antigravity — Phase 1 calibration & design revision
**Goal:** Address human design review: decouple truth from detectability, define attack-specific effect strata, resolve episode duration/interior window yield feasibility, report capacity by split and speed band with unique test aircraft, correct freeze oracle and report ramp + abrupt recall and FPR, compute train-only calibration thresholds, treat 15+ m/s vertical-rate band separately, check 90s freeze feasibility, and clarify Eq. 12 noise semantics.
**Done:**
- Extended and optimized `scripts/calibrate_v3_stage1.py` (cached group indices, pure numpy vectorized shifts; completed read-only in ~40 seconds).
- Generated `docs/calibration_v3_stage1.json` (report_version 4) with all 8 requirements covered.
- Revised `docs/attack_v3_design.md` (Draft 4) and `configs/attack_v3_stage1.yaml` (Draft 4).
- Appended D-019 to `docs/DECISIONS.md`, superseding effect-gate and window-rule portions of D-011, D-014, and D-018.
- Updated `docs/PROJECT_CONTEXT.md` and `docs/ROADMAP.md`.
**Ran / verified:**
- Verified calibration rerun on immutable `opensky_clean_v1.parquet` and `split_aircraft.json`.
- Train-only p95 thresholds: 0--50 m/s: 491.91 m (+2.22 m vs all), 50--100 m/s: 919.12 m (+0.67 m), 100--200 m/s: 1883.64 m (-7.11 m), 200+ m/s: 2505.35 m (-7.99 m). Geo glitch threshold: 2887.98 m (1,460 rows).
- Altitude 15+ m/s vertical-rate band: train baro p95 373.38 m vs all 225.45 m (+147.9 m divergence); recommended separate descriptive reporting.
- Segment length feasibility: 21,389 segments total; 16,171 >= 360 s (75.6%), 12,616 >= 600 s (59.0%), 10,139 >= 900 s (47.4%).
- Window yields: nominal 120 s episodes (12 rows) produce 0.0 interior-only windows for 30-row windows; 600 s produces mean 2.50 interior-only windows (7.85 qualifying); 900 s produces mean 5.50 interior-only windows (10.84 qualifying).
- 90 s freeze feasibility: 9 rows with 3-step ramp has 3 interior rows; cannot yield interior-only 30-row windows; evaluable at boundary+interior stratum only.
- Test speed band capacity: partial replay 120 s episode starts has 27 unique aircraft in 0--50 m/s band; marked descriptive only (< 100 aircraft).
- Oracle detector: gross abrupt recall 0.9999 (satisfies >= 0.99 release gate); gross 3-step ramp recall 0.9754; clean control FPR 4.58% (manipulation/freeze) and 3.87% (replay). Freeze interior step recall is 21.17% (expected displacement v * dt >= p95).
- Eq. 12 noise semantics: effective noise standard deviation is kappa * 25.0 m.
**NOT verified:** No attack generation code was written or executed; no dataset or sequence file was modified. All values remain proposed pending human approval.
**Results:** `docs/calibration_v3_stage1.json`.
**Problems / surprises:** The initial rerun of the previous calibration script had heavy allocation overhead in segment iteration (`df["time"].to_numpy()` inside loop); optimized with precomputed groupby indices and pure vectorized shifts, reducing runtime from minutes to ~40 seconds.
**Decisions made:** D-019 proposed (superseding effect-gate and window-rule portions of D-011, D-014, D-018).
**Next steps:** Human review and approval of Draft 4 design, Draft 4 YAML, and D-019. Once approved, proceed to Phase 1 attack generator framework implementation.
**Questions for human:** Do you approve the Draft 4 design, Draft 4 YAML, and proposed decision D-019?

### 2026-10-20 — Session 9 — Claude Code — Phase 1 foundation
**Goal:** Implement the approved Phase 1 foundation only: config approval gate, natural keys, input fingerprints, deterministic seeding, fixed-split access, output schemas, and manifest skeleton; tests first; no attack operations or dataset generation.
**Done:** Added `src/flids/attacks/{config,keys,fingerprint,seeding,splits,schemas,manifest}.py`, package `__init__` files, and `tests/conftest.py`; added synthetic tests `tests/test_{config,keys,fingerprint,seeding,splits,schemas,manifest}.py`; wrote `scripts/check_foundation_on_real_data.py` (not run); pinned `pyyaml==6.0.3` in `requirements.txt`; appended D-020; updated ROADMAP and PROJECT_CONTEXT; committed code, tests, and docs.
**Ran / verified:** `pytest -q` -> `61 passed in 1.23s` (module runs: config 7, keys 8, fingerprint 8, seeding 9, splits 8, schemas 15, manifest 5). Real YAML load: required keys OK, version `attack_v3_stage1_draft_4`, status `proposed_unapproved`; `require_approved` refused as expected. PyYAML 6.0.3 installed in `.venv`.
**NOT verified:** `scripts/check_foundation_on_real_data.py` was not run (per instruction); therefore real-table natural-key uniqueness, real content/schema fingerprints, and split coverage were not re-measured this session (split format was inspected: 9,995/2,142/2,142 = 14,279 unique). No attack dataset, model training, or sequence artifact was produced.
**Results:** No experiment; no E-### entry.
**Problems / surprises:** `.venv` is Python 3.13.2 although `requirements.txt` labels the environment Python 3.12; the PyYAML wheel is cp313. PyArrow returned a `ChunkedArray` for pandas 3.0 string columns, fixed with `combine_chunks()` in the string fingerprint encoder.
**Decisions made:** D-020 (APPROVED): design approvals listed there; tier magnitudes, altitude shifts, and quota cell matrix remain provisional.
**Next steps:** Human runs `scripts/check_foundation_on_real_data.py` and reviews its summary. Then implement attack operations (episode placement, constant/Gaussian/gradual deviation, replay, freeze) only after provisional values are approved or explicitly parameterized. Do not flip the YAML status until then.
**Questions for human:** Confirm the real-data check output; confirm when tier magnitudes, altitude shifts, and quota cells are approved so the YAML status can change to `approved`.


### 2026-10-20 — Session 10 — Claude Code — Phase 1 kinematics, eligibility, and placement
**Goal:** Continue the Phase 1 foundation with housekeeping fixes, kinematics, row/pair/window eligibility, replay-source lookup, deterministic episode placement, and a read-only real-data check script; tests first; no attack operations, dataset generation, or model training.
**Done:**
- Housekeeping: `manifest.git_dirty()` (from `git status --porcelain`), `int()` coercion of `segment_id` before seeding, and `NaturalKeyError` on null `icao24`/`segment_id`; one test each.
- Added `src/flids/attacks/kinematics.py`: vectorized speed bands (`missing`, `invalid`, lower-inclusive) and `pair_residual_m` with antimeridian wrapping and the calibration metre convention.
- Added `src/flids/attacks/eligibility.py`: provisional per-family `REQUIRED_FIELDS`, `row_eligible` (airborne, contact lag 0--30 s and flag, observed value and flag), `pair_valid` (same group, `0 < dt <= 30`), `eligible_starts` (prefix sums, caller-built masks), and `replay_source_offsets` (pure, nearest to `t - 300 s`, tie to earlier, source must be eligible, target-independent).
- Added `src/flids/attacks/placement.py`: `rows_for_duration` (`duration // 10`), provisional span filter `0.8x`--`1.25x`, per-request RNG placement with max 3 per segment, 600 s minimum gap, and full accept/reject accounting.
- Added tests `tests/test_kinematics.py` (9), `tests/test_eligibility.py` (15), `tests/test_placement.py` (14).
- Wrote `scripts/check_eligibility_on_real_data.py`; NOT run. It reports calibration-style vs strict eligibility and replay availability, 30-row stride-10 capacities, flag/NaN disagreement, `|dlon| > 180` pairs, wrapped residual quantiles vs train-only p95, span-filter removals, and adjacent-pair dt quantiles.
- Appended D-021; updated ROADMAP and PROJECT_CONTEXT.
**Ran / verified:** Module runs: kinematics `9 passed in 0.94s`; eligibility `15 passed in 0.81s`; placement `14 passed in 0.25s`. Full suite: `104 passed in 1.59s`. The real-data script was syntax-checked with `py_compile` only.
**NOT verified:** No real-data result was produced; all real-data counts, replay-convention differences, span-filter removal counts, and dt distributions remain unmeasured until the human runs `scripts/check_eligibility_on_real_data.py`. No attack dataset, sequence artifact, or model was produced.
**Results:** No experiment; no E-### entry.
**Problems / surprises:** Pandas 3.0 returns read-only arrays from `to_numpy()`, so `pair_valid` copies before clearing the first element. The first prefix-sum implementation had mismatched pair-count slices; replaced with explicit start-index arrays. Eligibility tests initially exposed a broadcast error, fixed before any real data were involved.
**Decisions made:** D-021 (approved session amendments; `REQUIRED_FIELDS` and span factors provisional).
**Next steps:** Human runs `scripts/check_eligibility_on_real_data.py` and reviews its report. Then, after provisional tier/shift/quota values are approved or explicitly parameterized, implement row-level attack operations and episode generation. Do not flip the YAML status yet.
**Questions for human:** Do the reported foundation counts match the calibration references? Approve the provisional `REQUIRED_FIELDS` and span factors, or request changes before attack operations begin?

### 2026-10-21 — Session 11 — Claude Code — Phase 1 ramps and manipulation primitives (Session 3a)
**Goal:** Add the approved housekeeping fixes plus pure ramp and manipulation primitives for one segment, tests first, with no replay, freeze, gradual deviation, window labelling, dataset generation, or training.
**Done:**
- Housekeeping: placement now tracks starts pruned by overlap and reports `"overlap"` when earlier accepted episodes exhaust the remaining starts; `pair_valid` asserts rows are sorted by `(icao24, segment_id, time)` and rejects null keys; `schema_fingerprint` canonicalises object/`str`/`string`/Arrow-string dtypes to `"string"` (pandas 2 vs 3 stable) while keeping non-string dtypes distinct.
- Added `src/flids/attacks/ramps.py`: `ramp_multipliers(n_rows, ramp_rows=3, mode)` for `linear_mix` (quarter steps `k/(ramp_rows+1)`, mirrored offset, minimum `2*ramp_rows+1` rows) and `abrupt` (all 1.0, first `onset`, last `offset`); attack (`a>0`) and effective (`a>=0.5`) mask helpers.
- Added `src/flids/attacks/manipulation.py`: `constant_horizontal`, `gaussian_horizontal`, `eq12_noise`, `altitude_constant`, `manipulation_streams`, and the shared `ManipulationResult`. Displacement uses the amended kinematics conversion; inputs are copied; active rows must be finite; metadata/flags are never touched; bearings are `[0, 360)` and 360 raises; latitude overflow and altitude outside `[-500, 20000]` m reject rather than clip.
- Added tests `tests/test_ramps.py` (8) and `tests/test_manipulation.py` (36), plus four housekeeping tests. Extended `scripts/check_eligibility_on_real_data.py` with a read-only capacity-attribution block (segment-relative offset-mod-10 vs every-10th-valid-start vs global-index alignment, cross-segment-boundary windows, and row-mask variants).
- Appended D-022; updated ROADMAP and PROJECT_CONTEXT.
**Ran / verified:** `tests/test_ramps.py` -> `8 passed in 0.36s`; `tests/test_manipulation.py` -> `36 passed in 2.44s`; `tests/test_placement.py` -> `15 passed in 0.49s`; `tests/test_eligibility.py` -> `17 passed in 2.26s`; `tests/test_fingerprint.py` -> `9 passed in 2.48s`; full suite `152 passed in 4.53s`. `scripts/check_eligibility_on_real_data.py` was syntax-checked with `py_compile` only.
**NOT verified:** The real-data script was not run, so the 3.5% attribution, cross-boundary window counts, row-mask variant counts, and the existing eligibility/residual/spans reports remain unmeasured. No attack episodes, datasets, sequence artifacts, or models were produced. The corrected magnitude/4 ramp oracle recall is not computed; it belongs to Gate 1b.
**Results:** No experiment; no E-### entry.
**Problems / surprises:** A ramp error message did not match the planned "at least" wording; fixed before final runs. Pandas 3.0.1 maps Python strings to a `str`/`StringDtype` rather than `object`, which the new schema canonicalisation handles.
**Decisions made:** D-022 (approved with amendments; tier magnitudes, sigmas, kappa, and altitude shifts remain provisional).
**Next steps:** Human runs `scripts/check_eligibility_on_real_data.py` and reviews the attribution output. Then, if authorized, integrate these primitives into episode generation; Gate 1b must recompute the ramp oracle with magnitude/4. Do not start replay, freeze, gradual deviation, window labelling, or the dataset writer without approval.
**Questions for human:** Does the attribution output explain the reported train-stride gaps? Confirm the D-022 conventions before episode integration.

### 2026-10-21 — Session 12 — Claude Code — Phase 1 composition, gradual, replay, freeze, detectability (Session 3b)
**Goal:** Add pure displacement composition, gradual deviation, delayed replay, freeze, and detectability helpers for one episode, tests first, with no assembler, window labelling, writer, dataset generation, or training.
**Done:**
- `manipulation.py`: added `horizontal_displacement_constant`, `horizontal_displacement_gaussian`, `apply_horizontal_displacement`, `add_scaled_eq12_noise`, and `gradual_horizontal`; `constant_horizontal` and `gaussian_horizontal` are now thin wrappers. Eq. 12 noise is applied to displacement components before conversion and scaled by `a_t`; Stage 1 has horizontal noise only (D-023).
- `ramps.py`: added `effective_row_count(realized_multipliers)` (`>= 0.5`).
- New `replay.py`: `replay_fields` with original-array sources, `(1-a)*current + a*source`, shortest-arc heading/longitude, strict `0 <= source < i`, whole-episode `"no_replay_source"` rejection, per-row delays, and partial/full field constants.
- New `freeze.py`: `freeze_lat_lon` and `anchor_from_offsets` (strictly before start, finite values, default 30 s age limit, `None` when unusable).
- New `detectability.py`: `residual_series` (pair `(k-1, k)`, earlier row's velocity/heading, first `NaN`) and `injected_displacement_m`.
- Tests: `tests/test_composition.py` (14), `tests/test_replay.py` (17), `tests/test_freeze.py` (13), `tests/test_detectability.py` (6), plus two `effective_row_count` tests in `tests/test_ramps.py`. Pre-refactor wrapper outputs were captured as float-hex references from commit 3b64bb0 before any edit.
**Ran / verified:** `tests/test_composition.py` -> `14 passed`; `test_replay.py` -> `17 passed`; `test_freeze.py` -> `13 passed`; `test_detectability.py` -> `6 passed`; `test_manipulation.py` -> `36 passed`; `test_ramps.py` -> `10 passed`; full suite -> `204 passed in 2.25s`. Wrapper outputs are bit-for-bit identical to the pre-refactor implementation. The mandatory 60-row/delay-30 test passes, and the delay-10 test fails under an in-place implementation by construction.
**NOT verified:** No real data touched; no episode assembler, window labels, dataset writer, sequence artifact, or model exists. The 5-effective-row rejection and `"no_freeze_anchor"`/`"insufficient_effective_rows"` handling are not implemented (Session 3c). `add_scaled_eq12_noise` was checked statistically, not against Li et al.
**Results:** No experiment; no E-### entry.
**Problems / surprises:** The `[-180, 180)` wrap can round to `+180.0` for tiny negative inputs; replay and freeze map the `+180` endpoint to `-180` and heading maps `360` to `0`. The existing D-022 `_new_longitude` was left unchanged to preserve bit-exact wrapper outputs.
**Decisions made:** D-023 (approved with six session amendments; tier values remain provisional).
**Next steps:** Session 3c may build the episode assembler around these primitives, including `"insufficient_effective_rows"` and `"no_freeze_anchor"` rejection. Gate 1b still must recompute the ramp oracle with `magnitude/4`. Do not start window labelling, the dataset writer, or generation without approval.
**Questions for human:** Confirm the realized-multiplier effective-row convention and the 30 s anchor-age limit before the assembler consumes them. Should partial replay treat a missing source for an active row as an episode rejection (current) or as a candidate rejection at placement time?

### 2026-10-21 — Session 13 — Claude Code — Phase 1 episode assembly, no-op guard, and window labelling (Session 3c)
**Goal:** Compose the D-022/D-023 primitives into one in-memory episode, enforce the effective-row and no-op rules, label v2-anchored windows, add the sixth schema table, and write (not run) the real-data window-yield check. No assembler, selection logic, writer, CLI, dataset, or training.
**Done:**
- New `episode.py`: frozen `EpisodeSpec` and `EpisodeResult`, and `build_episode` for all seven families. It returns episode-relative values for target fields, realized multipliers, positions, replay delays, changed fields, injected horizontal/altitude change, and a summary; inputs are never mutated.
- Rejections (never raised): `latitude_out_of_range`, `altitude_out_of_range`, `no_replay_source` (defensive, logged), `no_freeze_anchor`, `insufficient_effective_rows` (< 5 realized `a_t >= 0.5`), `replay_delay_mismatch`, and `no_measurable_change`.
- Provisional no-op guard: `NOOP_MIN_HORIZONTAL_M = 100.0`, `NOOP_MIN_ALTITUDE_M = 30.0` over effective rows; horizontal families/freeze use `injected_displacement_m`, the altitude family uses altitude change, and replay counts both (full replay accepts any measured field).
- New `windows.py`: `label_windows` mirrors v2 (30 rows, stride 10, start 0, full windows only); labels `normal`/`attacked`/`ambiguous` with the >= 5 effective-row rule, strata `none`/`boundary`/`interior_only`, and an overlap assertion.
- `schemas.py`: added the `windows` table with label/stratum enums and documented that `ramp_multiplier` is the realized multiplier.
- New `scripts/check_windows_on_real_data.py`: read-only, WRITTEN BUT NOT RUN; 120/600/900 s placements on 1,000 seeded train segments with comparisons to 7.85/10.84 attacked and 2.50/5.50 interior-only windows.
- Tests first: `tests/test_episode.py` (16), `tests/test_windows.py` (11, including a brute-force reference and exact counts), and three new `tests/test_schemas.py` cases (20 total).
**Ran / verified:** `tests/test_episode.py` -> `16 passed`; `tests/test_windows.py` -> `11 passed`; `tests/test_schemas.py` -> `20 passed`; full suite -> `236 passed in 1.19s`; `py_compile` on the new modules and script -> `compile ok`. Episode end-to-end fixtures cover all seven families, every rejection reason, Gaussian + Eq. 12 manual composition, input immutability, metadata isolation, and same-seed determinism. Window tests confirm 12-row episodes have no interior-only windows, a 60-row aligned episode has exactly two (starts 40 and 50), a 9-row episode has 7 effective rows, and weak overlap is ambiguous.
**NOT verified:** No real data touched; the window-yield script has not been run, so no comparison with the calibration means exists. No dataset assembler, selection logic, writer, CLI, sequence artifact, or model exists. No episode is persisted anywhere. The no-op thresholds and all tier values remain provisional and untested against real aircraft.
**Results:** No experiment; no E-### entry.
**Problems / surprises:** Ramp rows blend replay values, so the episode-level replay fixture asserts exact source values only on interior rows and checks the 0.25 blend separately. Test draft fixtures initially used 5-row episodes, which `linear_mix` correctly rejects (minimum 7, and 5 effective rows anyway); changed to 9-row episodes.
**Decisions made:** D-024 (approved session answers; no-op thresholds provisional).
**Next steps:** If the human approves, run `scripts/check_windows_on_real_data.py` and reconcile any window-yield differences before building the assembler. Gate 1b still must recompute the ramp oracle with `magnitude/4`. Do not start the dataset assembler, selection logic, writer, CLI, or generation without approval.
**Questions for human:** Are the provisional no-op thresholds (100 m horizontal / 30 m altitude) acceptable for Stage 1? Should full-field replay with a measurable source difference only in velocity/heading/vertrate remain a `"no_measurable_change"` rejection (current), or should any changed field count?

### 2026-10-22 — Session 3d-1 — Codex — Pure in-memory overlay assembler
**Goal:** Add only the approved in-memory assembler and three housekeeping fixes; no dataset, writer, manifest writer, CLI, real-data run, or training.
**Done:** Added isolated `parameter_rng`; `build_episode` now rejects an ineligible interval; baro-only altitude no longer requires geoaltitude. Added `assembler.py` with `OverlaySpec`, deterministic selection/episode IDs, eligibility/replay/glitch screens, placement/build rejection rows, complete row/step/episode/provenance/window/segment tables, and schema validation. Added `segments` schema, synthetic assembler tests, and an unrun read-only `check_assembler_on_real_data.py` covering 300 train segments and seven families.
**Ran / verified:** Focused housekeeping tests: 66 passed. Full suite: 247 passed in 3.99 s. `py_compile` passed for the assembler and check script.
**NOT verified:** The real-data script was not run; no data or results were written. No writer, manifest writer, CLI, quota/density mode, ghost/DoS implementation, or training was added.
**Results:** No experiment; no E-### entry.
**Problems / surprises:** None after the direct altitude API compatibility test was retained.
**Decisions made:** D-025.
**Next steps:** Human review of the pure assembler and authorization before any writer or real-data check.

### 2026-10-22 — Session 3d-2 — Codex — Assembler review fixes
**Goal:** Verify and fix review findings without a writer, CLI, generated dataset, training, or real-data run.
**Done:** Confirmed and fixed replay source IDs (now global source-row IDs), separated placement from build RNG streams, returned accepted request indexes, added stream golden tests, made provenance JSON strict, and strengthened shuffled-input/natural-key, replay, and ID-uniqueness tests. D-026 records behavior changes and deferred metadata.
**Ran / verified:** Newly added tests first failed at collection before missing APIs existed; focused review suite then passed 33 tests. No `check_*_on_real_data.py` script was run.
**NOT verified:** No real data, generated data, results, writer, manifest writer, CLI, quota/density mode, ghost/DoS, or training was touched. The `speed_band` and freeze-anchor metadata remain unfilled by design.
**Results:** No experiment; no E-### entry.
**Problems / surprises:** Three nearby accepted episodes can produce windows overlapping two episodes; `label_windows` correctly asserts rather than assigning an ambiguous single episode ID. The ID-uniqueness test therefore retains the configured 600-second gap.
**Decisions made:** D-026.
**Next steps:** Resolve the questions below before changing selection semantics or multi-episode defaults.
**Questions for human:**
1. Selection `u` currently depends only on `(global_seed, icao24, segment_id)`, so same-seed overlays at the same tau select identical segments. Recommend an explicit per-overlay key in entropy, recorded in the future manifest: it prevents cross-overlay segment/class confounding and episode-ID collisions when merging overlays, but makes selections non-nested. Alternatives are a manifest-recorded per-overlay seed (similar effect, weaker compositional clarity) or deliberate nested selection (keeps nesting but increases confounding when overlays are merged). Which should be adopted?
2. Should `eta_requested` remain this implementation's Bernoulli `tau`, or should it represent the paper's Eq. 10 density/strength eta? Recommend retaining `tau` as selection probability and adding separately named paper parameters only after the equation mapping is approved.
3. For 900-second episodes with a 600-second minimum gap, many requests will reasonably reject as `gap_violation`. Recommend one episode per segment for 900 s (or reduce requests to two only for segments with demonstrably sufficient span); approve a different default only with an explicit capacity study.

### 2026-10-22 — Session 3d-3 — Codex — Missing-value-safe overlay tables
**Goal:** Fix the real-data assembler schema failure and all-NaN cell-median warnings without running real-data scripts or changing attack logic.
**Done:** Fixtures now use true NaN feature values and include an all-missing-position segment. Feature originals/modifications are nullable; `contact_lag_seconds` is nullable because `build_dataset.py` derives it from nullable `lastcontact`. Added finite-only cell median returning `unknown`, strict provenance/unchanged-NaN checks, and D-027.
**Ran / verified:** New missing-data tests first failed: 7 failed and emitted 7 all-NaN median warnings at the reported schema failure. Focused rerun passed 31 tests.
**NOT verified:** No data files or `check_*_on_real_data.py` script were touched/run. Real-table `onground` null status is unverified; it remains non-nullable. No writer, CLI, dataset, training, or attack/selection/RNG change was made.
**Results:** No experiment; no E-### entry.
**Problems / surprises:** Beyond the reported feature failure, code inspection confirmed `contact_lag_seconds` can be null when `lastcontact` is null, despite the paired missingness flag.
**Decisions made:** D-027.
**Next steps:** Re-run the real-data check only when explicitly authorized; if it exposes null `onground`, decide whether to reject or represent it as nullable rather than coercing it silently.
