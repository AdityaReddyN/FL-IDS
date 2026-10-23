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

### 2026-10-22 — Session 4a — Codex — Stage A parameter review and assembler validation
**Goal:** Complete Stage A only on `phase1-generation`: verify baseline tests, provide the parameter approval sheet, run the requested read-only 300-train-segment diagnostic, and stop for human approval.
**Done:** Added `scripts/make_approval_sheet.py`. Added overlay-keyed selection entropy, renamed the episode schema field to `tau_requested`, and clarified in config/docs that tau is a Bernoulli eligible-segment probability rather than paper Eq. 10 eta. Recorded deterministic merge contract: lexicographic overlay-key order, at most one overlay per segment, conflicts logged as `overlay_conflict`. Kept config status `proposed_unapproved`.
**Ran / verified:** Branch `phase1-generation`; baseline suite `253 passed in 4.30s`. Focused updated tests `47 passed`. Approval sheet printed all listed proposed tiers, sigmas, kappas, altitude shifts, quotas, required fields, span/no-op thresholds, durations, ramp and other provisional values. `python -W ignore::RuntimeWarning scripts/check_assembler_on_real_data.py` equivalent via the repository venv completed for 300 seeded train segments per each of seven families; no schema/NaN error occurred. Selection fractions at tau=.2: constant .2222, Gaussian .2667, gradual .2000, altitude .2044, partial replay .1714, full replay .1881, freeze .2370. Rejections: gradual 27 `insufficient_effective_rows`; freeze 2 `no_freeze_anchor`, 5 `no_measurable_change`; none reported for the other four. Each per-family table peak Python memory was about 116.1–124.6 MB.
**NOT verified:** No Stage B work, dataset, manifest, writer, CLI, plausibility report, plot, or training was performed. No values were tuned. The diagnostic is a small-sample pipeline check; its selection fractions and performance extrapolations are not scientific results. The config remains unapproved.
**Results:** Diagnostic only; no E-### experiment entry.
**Problems / surprises:** Gaussian overlay assembly was much slower than other families: 126.45 seconds per 100 sampled segments, extrapolating to about 27,046 seconds for all 21,389 segments. Other families were approximately 10.42–11.56 seconds per 100. Gradual 120-second episodes were all rejected under the existing five-effective-row rule (12-row gradual episodes yield only four effective rows). The real-data run passed schema validation despite source missingness.
**Decisions made:** D-028.
**Next steps:** Human reviews the approval sheet values, selects/approves parameter values, and changes YAML status to `approved`. Stop here until that gate is satisfied.

### 2026-10-22 — Session 4b — Codex — New-chat project handoff
**Goal:** Create a portable context document so a new chat can learn the project mission, current implementation, scientific constraints, decisions, gates, and exact Phase 1 next steps.
**Done:** Added `docs/CHAT_HANDOFF.md` with a repository navigation guide, current branch/config/worktree snapshot, data and E-001 baseline context, Phase 1 module map, D-020--D-028 summary, measured Stage A pipeline-validation notes, and Stage A/B/C gates. Linked it from `docs/PROJECT_CONTEXT.md`.
**Ran / verified:** Read `AGENTS.md`, project context, roadmap, latest progress entries, decisions, experiment registry, and attack design. Confirmed branch `phase1-generation`, latest commit `61edcca`, config `proposed_unapproved`, and untracked `.claude/` at snapshot time. No tests or data scripts were run; no data files were accessed.
**NOT verified:** No claim was made that a full suite passed after Stage A's D-028 changes. No new code, dataset, writer, manifest, CLI, or generation was added.
**Results:** Documentation only; no experiment and no E-### entry.
**Problems / surprises:** Git reported permission warnings for its user-level ignore file and `.pytest_cache/`; `.claude/` remains untracked and untouched.
**Decisions made:** None.
**Next steps:** Human approval of provisional Stage A parameters and setting `configs/attack_v3_stage1.yaml` to `approved` are still required before Stage B.

### 2026-10-22 — Session 4c — Codex — Approval-gate state check
**Goal:** Resume from the project handoff instructions and determine whether the next authorized Phase 1 stage may begin.
**Done:** Re-read the required repository context and verified the live branch, worktree, config status, and latest commit. Branch is `phase1-generation`; config remains `status: proposed_unapproved`; `.claude/` remains an unrelated untracked directory and was not touched. Stopped without starting Stage B or changing config.
**Ran / verified:** No tests, scripts, or data access. Read-only Git/config inspection only. Latest commit before this entry was `73fdc2d docs: add project chat handoff context`.
**NOT verified:** No full-suite run after Stage A D-028 edits; no Stage B or later work.
**Results:** None; no experiment and no E-### entry.
**Problems / surprises:** Git again reported permission warnings for the user ignore file and `.pytest_cache/`.
**Decisions made:** None.
**Next steps:** Human reviews the approval sheet, approves the listed parameter values (or explicitly approves the YAML values), and sets `configs/attack_v3_stage1.yaml` status to `approved`. Do not start Stage B before that change.

### 2026-10-22 — Session 4d — Codex — Stage 1 approval and Stage B infrastructure
**Goal:** Apply the human's explicit approval of all Draft 4 Stage 1 values and implement Stage B infrastructure without generating a dataset or running on real data.
**Done:** Recorded D-029 and set the YAML status to `approved`. Added a bit-exact seven-table assembler golden before refactoring, column-wise row/step construction, and a whole-segment chunk iterator. Added a create-only chunked Parquet writer with approved-config, clean-tree, and overwrite guards; per-table hashes/counts; input fingerprints; a manifest; and a descriptive plausibility report. Added a config-to-single-overlay mapping, count-only dry-run helper, CLI, and SVG plot script. D-030 documents two holds: cross-overlay conflict representation in the merged `segments` table, and a legacy nullable episode-ID rounding mismatch that is preserved by the golden.
**Ran / verified:** Baseline suite before implementation: 256 passed. New golden first failed with placeholder digests, then passed when frozen against the pre-refactor assembler. Direct comparison found the old row/step path rounded some int63 episode IDs through float64; the refactored path preserves that legacy output. New writer tests first failed before implementation, then passed. Full suite: `268 passed in 4.62s`. `py_compile` passed for changed modules and scripts; CLI `--help` displayed expected options. `git diff --check` passed.
**NOT verified:** No real-data scripts, dry-run on real data, writer invocation against the project data, dataset generation, model training, or Phase 1 output were run. Multi-overlay merge is not implemented; the writer is one overlay per run. Gate 1 is not passed.
**Results:** Synthetic pipeline tests only; no experiment and no E-### entry.
**Problems / surprises:** The legacy row/step `episode_id` can differ from the episode table for IDs above 2^53 because the old nullable conversion rounded through float64. Fixing it would break the requested bit-identical regression. The declared `segments` schema has a single selection draw/count despite independent overlay-specific eligibility and selection, so merged multi-overlay reporting needs a schema decision. Git continues to report permission warnings for the user ignore file and `.pytest_cache/`.
**Decisions made:** D-029 (human approval of Draft 4 values); D-030 (preserve golden and defer multi-overlay representation/ID correction pending human direction).
**Next steps:** Resolve D-030 before Stage C. Review Stage B implementation, decide whether to repair episode-ID rounding despite the golden, and choose how merged per-overlay selection/eligibility is represented. Stage C additionally requires a clean committed tree and explicit human go after Stage B review; `.claude/` remains unrelated and untracked.
**Questions for human:** (1) May the row/step episode-ID rounding be corrected, knowingly changing the pre-refactor golden, so all tables share exact episode IDs? (2) For merged multi-overlay output, should we add a per-overlay selection table or extend the `segments` schema with overlay-specific draws/eligibility (or another representation)?

### 2026-10-22 — Session 4e — Codex — Stage C authorization and gate check
**Goal:** Continue after the human reviewed Stage B and authorized the next stages, while respecting the Stage C clean-tree and Phase 1 Gate 1 requirements.
**Done:** Re-read project context and verified the live branch, worktree, config status, latest commit, and Phase 1 gate notes. Updated PROJECT_CONTEXT and ROADMAP to record the Stage B review and authorization; execution remains held by the unrelated untracked `.claude/` directory and unresolved D-030 choices.
**Ran / verified:** Branch is `phase1-generation`; config remains `status: approved`; HEAD is `6922b4b phase1: add Stage B single-overlay infrastructure`; worktree reports only `?? .claude/` (Git also warns about access to the user ignore file and `.pytest_cache/`).
**NOT verified:** No real-data check, dry-run, writer invocation, generation, sequence construction, training, or later-phase work was run. Gate 1 remains pending and no dataset exists.
**Results:** No experiment; no E-### entry.
**Problems / surprises:** The explicit go does not clear the writer's clean-tree requirement. The single-overlay writer also cannot implement the approved multi-overlay conflict contract until the selection-evidence representation in D-030 is chosen. Phase 2 must wait for Gate 1 review.
**Decisions made:** None.
**Next steps:** Preserve `.claude/`; the human must handle that unrelated untracked directory so the tree can be clean. Resolve D-030's episode-ID consistency and per-overlay selection representation; then Stage C may run under the received authorization. After generation, stop for Gate 1 review before Phase 2.
**Questions for human:** For D-030, approve correcting row/step episode IDs despite changing the frozen golden, and choose an added per-overlay selection table (recommended) or another representation for overlay-specific eligibility/selection evidence.

### 2026-10-22 — Session 4f — Codex — Stage B multi-overlay resolution
**Goal:** Resolve D-030 using the documented recommendation, then prepare the authorized seed-42 Stage C run without crossing Gate 1.
**Done:** Rechecked branch `phase1-generation` and found the worktree clean after the human handled `.claude/`. Corrected nullable int64 episode IDs and made episode/candidate IDs overlay-specific. Added `overlay_selections` as the eighth validated table, `overlay_key` to episodes/rejections, chunked multi-overlay assembly, lexicographic conflict resolution with one `overlay_conflict` rejection per losing request, multi-overlay writer counters/manifest, `config.json`, and a CLI defaulting to all seven Stage 1 families. Updated D-031, ROADMAP, PROJECT_CONTEXT, and CHAT_HANDOFF.
**Ran / verified:** New exact-ID and multi-overlay tests first failed before implementation (missing API); overlay-key provenance assertions also failed before the schema fields were added. Focused tests passed 21 across assembler/writer/run-config; the config-output assertion failed before implementation, then passed. Final full suite after all changes: 273 passed in 18.78s. `py_compile`, CLI `--help`, and `git diff --check` passed. No real-data or dataset writer run was performed.
**NOT verified:** Stage C output, runtime, manifest on actual input, physical plausibility values, plots from generated data, and all later phases. Gate 1 remains pending.
**Results:** No experiment; no E-### entry. Stage C has not run yet.
**Problems / surprises:** Correct exact episode IDs and overlay-specific hashing intentionally invalidate the Session 4d seven-table golden. The new frozen synthetic digest captures the corrected eight-table behavior. The CLI's default seven-family run uses the approved `moderate` tier and first configured tau (0.005); explicit flags can select a family/tier/tau.
**Decisions made:** D-031 implementation choice, authorized by the human's explicit go after the recommended resolution was stated.
**Next steps:** Run the full suite after the latest writer/config/CLI changes, check `--help`, commit all Stage B resolution code/tests/docs, confirm clean status, then invoke Stage C seed 42 only. After generation, review the written config, manifest, plausibility report, table schemas/counts/hashes, and plots; stop for human Gate 1 review before Phase 2.
**Questions for human:** None before the authorized seed-42 Stage C run; Gate 1 approval is still required before Phase 2.

### 2026-10-22 — Session 4g — Codex — Stage C config preflight correction
**Goal:** Start the explicitly authorized seed-42 Stage C run after D-030 resolution and a clean commit.
**Done:** Invoked the seed-42 CLI at the verified new output path. It failed before writer invocation because `run_config.py` read `gaussian` from the wrong YAML level. Updated the test fixture to match the approved YAML structure (`attacks.gaussian`) and corrected parameter mapping.
**Ran / verified:** The regression test first failed with `KeyError: gaussian`; after the fix, `tests/test_run_config.py` passed (3 passed). Full suite passed: 273 passed in 18.45s. The failed CLI attempt stopped before creating the output directory; no dataset files were written.
**NOT verified:** Real-data configuration execution after the fix, output directory creation, Stage C tables/manifest/report/plots, physical metrics, and Gate 1. No later phase was started.
**Results:** No experiment or dataset result; no E-### entry.
**Problems / surprises:** The approved YAML nests Gaussian settings under `attacks.gaussian`; the earlier synthetic fixture had the wrong top-level shape, masking this CLI mapping defect.
**Decisions made:** None.
**Next steps:** Commit the config-mapping fix and this status update; recheck the output target is absent and worktree clean; retry only seed 42 to `data/attack_generation_v3/stage1_seed_42`. Then inspect the generated result files and stop for Gate 1 review.
**Questions for human:** None before the authorized seed-42 retry; Gate 1 review remains required before Phase 2.

### 2026-10-22 — Session 4h — Codex — Stage C partial generation attempt
**Goal:** Retry authorized seed-42 generation after fixing the approved YAML mapping.
**Done:** Rechecked `phase1-generation`, approved config, clean Git status, and absent target. Started the multi-family writer at `data/attack_generation_v3/stage1_seed_42/`. The process remained CPU-active but produced no final outputs during the monitored interval; stopped it. Updated this context and the roadmap to mark the directory incomplete.
**Ran / verified:** The target was absent before invocation. During execution eight Parquet files appeared and some grew, but no `manifest.json`, `config.json`, or `plausibility_report.json` was written. The process was stopped; no complete dataset is available for Gate 1.
**NOT verified:** Table completeness, row counts, table hashes, schema validation after file closure, physical-plausibility metrics, plot generation, or any scientific property. The partial Parquet files are not a dataset and must not be consumed.
**Results:** No experiment/dataset result; no E-### entry.
**Problems / surprises:** Full-table generation is much slower than the small Stage A sample suggested, and the CLI has no chunk progress output. The writer is create-only, so the partial directory cannot be retried in place.
**Decisions made:** None.
**Next steps:** Keep the partial directory untouched. If continuing generation, commit this status update first and write seed 42 into a distinct new run directory; consider a measured performance optimization before another multi-hour attempt. After a complete run, validate artifacts and stop at Gate 1.
**Questions for human:** None; seed-42 generation remains authorized, but Gate 1 approval is still required before Phase 2.

### 2026-10-22 — Session 4i — Codex — Multi-overlay merge throughput optimization
**Goal:** Diagnose the slow seed-42 run and reduce avoidable merge work before retrying.
**Done:** The second seed-42 attempt ran for about 52 minutes, remained CPU-active, and was manually stopped. Its output directory has eight partial Parquet files without valid footers or manifest/config/report. Reworked `_merge_overlay_chunk` to precompute per-segment row-index maps once and slice tables by those indexes rather than repeatedly filtering every full chunk table for each segment. Preserved both partial output directories untouched. Updated project state and handoff notes.
**Ran / verified:** Focused assembler/writer tests: 19 passed in 9.31s. Full suite: 273 passed in 10.25s. The interrupted Parquet files were not accepted as valid datasets: a read-only footer check failed with missing Parquet magic/footer.
**NOT verified:** Throughput on the full real table after optimization, Stage C completion, table validators/hashes, plausibility report, plots, or Gate 1. No later phase was started.
**Results:** No valid experiment or dataset result; no E-### entry.
**Problems / surprises:** Large real-data runs have no progress output and PyArrow files remain incomplete until writer closure. CPU activity alone did not identify completed chunk counts; the interrupted files lacked valid footers and cannot be used or resumed.
**Decisions made:** None; D-031 semantics unchanged.
**Next steps:** Commit this optimization and documentation; confirm a clean tree; retry seed 42 only under a new run ID. If it again fails to make acceptable progress, do not continue blind—instrument/report chunk progress and optimize further before another generation attempt. Stop at Gate 1 after successful output.
**Questions for human:** None before the authorized seed-42 retry; Gate 1 remains required before Phase 2.

### 2026-10-22 — Session 4j — Codex — Stage C retry progress check
**Goal:** Continue the explicitly authorized seed-42 generation after the multi-overlay merge optimization.
**Done:** Started the writer in the new directory `data/attack_generation_v3/stage1_seed_42_retry2/` from clean commit `4969cba`. After about 33 minutes, stopped it before completion. Corrected the earlier observation that output had not advanced: the Parquet files had grown to about 50 MB. Read-only tail checks found no `PAR1` footer on any table, and there is no manifest/config/report, so this is not a usable dataset. Updated the snapshot and roadmap.
**Ran / verified:** Process was CPU-active. All eight expected Parquet paths existed and had grown; final sizes were 49,533,475 bytes attacked_rows, 3,327,779 step_labels, 997,302 overlay_selections, 416,443 episodes, 393,860 windows, 302,231 segments, 148,031 modified_row_provenance, and 60,287 rejected_candidates. Their final four bytes were not `PAR1`. No tests or real-data check script was run in this session.
**NOT verified:** Completed seed-42 dataset, readable Parquet metadata/row counts, manifest hashes, validators, plausibility report, plots, generation runtime, or Gate 1. No Phase 2 or training work was started.
**Results:** No valid dataset/experiment result; no E-### entry. The incomplete `stage1_seed_42_retry2/` directory is preserved and must not be consumed or overwritten.
**Problems / surprises:** A previous file listing rendered sizes blank; the files had in fact grown substantially. The stopped files still lack Parquet footer magic. A full-run throughput estimate is not established from this partial attempt.
**Decisions made:** None. D-031 semantics unchanged.
**Next steps:** Commit this status update; if continuing, run seed 42 into a new directory and allow the writer to complete. Validate the complete tables, manifest, report, and plots, then stop for human Gate 1 review. Do not start Phase 2 until Gate 1 is approved.
**Questions for human:** None; seed-42 generation is authorized. Gate 1 approval remains required before Phase 2.

### 2026-10-22 — Session 4k — Codex — Stage C full-run throughput hold
**Goal:** Allow the approved seed-42 generation a longer interval and determine whether the multi-overlay chunk writer can complete.
**Done:** Started a fresh run in `data/attack_generation_v3/stage1_seed_42_retry3/` from clean commit `64202bd`. Let it run for about one hour, then stopped it because no second chunk was visibly finalized. Preserved the partial directory. Read-only checks found no `PAR1` footer on any of its eight Parquet paths and no manifest/config/report. Updated the current snapshot and roadmap; Phase 2 was not started.
**Ran / verified:** The generator process remained responsive and CPU-active, with memory use varying roughly between 400 MB and 1 GB. After stopping, partial file sizes were: attacked_rows 28,590,908 bytes; step_labels 2,040,080; overlay_selections 673,847; episodes 249,041; windows 257,150; segments 202,726; modified_row_provenance 85,699; rejected_candidates 28,216. All lack the `PAR1` end marker. No tests or model training were run.
**NOT verified:** Complete dataset, readable Parquet metadata/row counts, manifest/table hashes, final schema validation, plausibility report, plots, physical metrics, or Gate 1. Full-run duration and cause of the slow chunk remain unverified. No later phase was started.
**Results:** No usable dataset or experiment; no E-### entry. `stage1_seed_42_retry3/` is incomplete and must not be consumed or overwritten.
**Problems / surprises:** The writer makes partial progress, but still had not finalized a second chunk after an hour; the output sizes become informative only after process stop. Current implementation lacks chunk-level progress reporting, so the exact slow operation is unknown.
**Decisions made:** None. D-031 semantics unchanged.
**Next steps:** Profile a representative chunk and add chunk-level timing/progress before another full-data attempt. Preserve all partial run directories. After a complete seed-42 run, inspect artifacts and stop for Gate 1 review; do not begin Phase 2 until approval.
**Questions for human:** None; Stage C seed-42 generation remains authorized. Gate 1 approval remains required before Phase 2.

### 2026-10-22 — Session 4l — Codex — Chunk progress instrumentation
**Goal:** Make Stage C chunk runtime observable before another full-data attempt.
**Done:** Added optional writer progress callbacks for chunk start/completion, elapsed and per-chunk seconds, cumulative/total segment counts, and cumulative row counts. The CLI streams these JSON events to stderr. The writer test verifies ordered progress and that expected row totals are unchanged.
**Ran / verified:** The new focused test first failed because `progress_callback` did not exist. After implementation, writer tests passed (6 passed). Full suite: 274 passed in 41.30s. CLI `--help`, `py_compile` for changed Python files, and `git diff --check` passed.
**NOT verified:** Full-data runtime, dataset generation, Parquet footer/manifest validation, plausibility report/plots, or Gate 1. No real-data check script or training was run.
**Results:** Synthetic test only; no experiment or E-### entry. No generated files created by this change.
**Problems / surprises:** The previous attempt did process data, but without progress events its slow operation and chunk number were unclear.
**Decisions made:** None; diagnostics do not change output contents or attack semantics.
**Next steps:** Commit the instrumentation and docs; then retry seed 42 into a new output directory using the explicit chunk progress. Use observed chunk timings to decide whether further profiling/optimization is needed. Validate complete outputs and stop for Gate 1; do not start Phase 2 until approval.
**Questions for human:** None before authorized seed-42 retry; Gate 1 approval remains required before Phase 2.

### 2026-10-23 — Session 4m — Codex — Stage C seed-42 generation complete
**Goal:** Complete the explicitly authorized seed-42 Stage C generation, verify the outputs, and prepare the Phase 1 Gate 1 review without crossing the gate.
**Done:** Ran the approved all-family CLI from clean commit `72958b0` into `data/attack_generation_v3/stage1_seed_42_retry4/`, using 64-segment chunks and chunk progress diagnostics. The process completed all 335 chunks and wrote the manifest, config, plausibility report, and eight Parquet tables. Ran the sanity plot script; it wrote six SVGs. Updated the snapshot and roadmap.
**Ran / verified:** Before the real-data run, full suite passed: 274 passed in 41.30s; focused writer tests: 6 passed; CLI `--help`, `py_compile`, and `git diff --check` passed. After generation, independently verified all eight Parquet footers, row counts, SHA-256 hashes, canonical column order/types, `git_dirty=false`, and manifest commit `72958b07de012a15520788aaa445aabf6591878a`. Manifest counts: attacked_rows 2,970,285; step_labels 2,970,285; episodes 263; rejected_candidates 63; modified_row_provenance 3,142; windows 246,200; segments 21,389; overlay_selections 149,723. Accepted episodes: altitude 59, constant 39, freeze 44, Gaussian 49, full replay 29, partial replay 43. Rejections: `insufficient_effective_rows` 48, `no_measurable_change` 7, `overlay_conflict` 4, `no_freeze_anchor` 3, `altitude_out_of_range` 1. Plot script wrote six SVGs.
**NOT verified:** No human Gate 1 approval; no Phase 2 sequence dataset, shortcut audit, training, or later phases. Physical plausibility remains descriptive, with no approved pass/fail cutoffs. RF replay fidelity, raw ADS-B bit-level effects, receiver signal strength/processing, and multi-receiver multilateration remain unavailable.
**Results:** Pipeline output only; no scientific result and no E-### entry. The dataset is under ignored `data/` and was not committed.
**Problems / surprises:** All 48 selected gradual-deviation candidates were rejected as `insufficient_effective_rows`; the approved nominal duration is 120 seconds and the acceptance rule requires five effective rows. Thus there are zero accepted gradual episodes and no gradual-deviation SVG; six of seven requested family plots were written. Parquet schema strings are encoded as Arrow `large_string` by pandas 3/PyArrow 26; names and canonical logical types match the declared schemas. This is not treated as a schema error.
**Decisions made:** None. Do not change approved YAML parameters or the five-effective-row rule without a new human decision.
**Next steps:** Human reviews [manifest.json](../data/attack_generation_v3/stage1_seed_42_retry4/manifest.json), [plausibility_report.json](../data/attack_generation_v3/stage1_seed_42_retry4/plausibility_report.json), and the six SVG plots under `plots/`; decide whether the zero-gradual-episode outcome is acceptable or whether a parameter/rule revision is authorized. Stop here; do not begin Phase 2 until Gate 1 is explicitly approved.
**Questions for human:** (1) Is the Stage C manifest/report and six-plot output approved for Gate 1 despite no accepted gradual episodes? (2) If not, may the approved duration/episode rule be revised to permit gradual episodes, or should Phase 1 retain zero gradual examples?

### 2026-10-23 — Session 4n — Codex — Phase 2 sequence pipeline and shortcut audit
**Goal:** Accept the user-authorized Gate 1 transition, build the first Phase 2 sequence dataset from the verified seed-42 Stage C tables, and run the prescribed shortcut diagnostics. No Phase 3 model training.
**Done:** Recorded human Gate 1 acceptance and Phase 2 conventions in D-032; added `src/flids/data/sequences_v3.py`, `scripts/build_sequences_v3.py`, `scripts/audit_shortcuts_v3.py`, and seven tests. The builder inherits the Stage C aircraft split/window labels, emits 15-channel windows (8 continuous + 7 missing flags), uses unique train-window source rows for train-only mean imputation/scaling, preserves ambiguous labels as -1, retains binary/multiclass labels, and writes a realistic split view plus seeded binary-balanced indices. Retained `onground`, contact lag and a configured stale flag in auxiliary arrays, not model input. The first audit exposed a large missingness shortcut; D-033 added deterministic missing-count matching for balanced training and a separate matched validation audit index, without changing realistic arrays or Phase 1 parameters. Updated `.gitignore` so source code under `src/flids/data/` is trackable despite the root `data/` ignore. Updated ROADMAP, PROJECT_CONTEXT, DECISIONS, attack design status, handoff, and E-002 registry.
**Ran / verified:** Tests first: initial collection failed because the Phase 2 module was absent; after implementation focused tests passed, then the new matching test failed before its field was implemented (5 passed/1 failed), then focused tests passed (7 passed). The first full-suite attempt had 247 passed and 32 setup errors because pytest could not create temp directories under the sandbox Temp path; reran with a repository-local basetemp, final full suite **281 passed in 12.09s**. Ran `py_compile` on the three new Python files, CLI `--help`, and `git diff --check`. Built canonical `data/sequences_v3/seed_42_phase2/` (ignored, not committed): train 170,767; val 37,712; test 37,721; 1,000 balanced train indices (500 normal/500 attack). Validation matched slice has 258 windows (129/129). Read-only validation confirmed all X arrays finite, all manifest table hashes match, balanced and matched-view missingness counts match exactly, and source splits stay separate. E-002 audit from `results/E-002/shortcut_audit_seed42_final.json`: missingness-only ROC-AUC 0.417674 on natural validation and 0.507331 on matched validation; position-only 0.507595; per-feature-summary 0.602075 natural and 0.604531 matched. Natural validation attack prevalence is 0.003424; 36 ambiguous validation windows are excluded from these binary audit scores. Builder config records source hashes, library versions, seed 42, commit `957a262`, and `builder_git_dirty=true`.
**NOT verified:** Gate 2 is not passed: per-feature summary statistics remain informative and realistic validation/test preserve natural missingness imbalance. No held-out-test shortcut score was computed; no model training, Phase 3 work, multi-seed audit, independent contact-lag leakage study, or gradual-class performance was run. These are pipeline checks over synthetic attack labels on decoded OpenSky state vectors, not scientific or operational-performance results. The first random-balanced output and the intermediate matched output are preserved under separate ignored directories; only `seed_42_phase2` is current.
**Results:** E-002 is marked done as a completed pipeline run, not as a Gate 2 pass. Full dataset counts and file hashes are in the ignored sequence manifest; audit metrics are copied from the result JSON. No model weights or datasets were committed.
**Problems / surprises:** Natural validation had 129 attacked and 37,547 normal windows; mean missing-cell counts were 3.07 for attack and 57.46 for normal, explaining the initial missingness-only ROC-AUC 0.6819. After matching train windows, missingness-only validation was near chance (0.5073 on the matched slice). Per-feature summary statistics remained modestly informative (0.6045 matched). Seed 42 has no gradual examples (class ID 3 remains declared but absent). First builder attempt was interrupted before writing because repeated pandas row access was slow; precomputed NumPy segment arrays reduced final build to about one minute. No immutable input or existing results directory was modified.
**Decisions made:** D-032 (human accepted Gate 1 and authorized Phase 2); D-033 (implementation choice for missingness-matched train/audit views; realistic evaluation arrays preserved).
**Next steps:** (1) Investigate per-feature-summary signal by attack family and determine whether it is expected attack signal or a residual shortcut, without changing approved Phase 1 parameters. (2) If a mitigation is authorized, implement it test-first and rerun the validation audit. (3) Only after shortcut criteria are reviewed and pass, prepare the Gate 2 review; do not start Phase 3 before approval.
**Questions for human:** Should the per-feature-summary ROC-AUC around 0.60 be treated as expected measurable attack signal, or must Phase 2 further condition the audit/evaluation to make it near chance before Gate 2?

### 2026-10-23 — Session 4o — Codex — Phase 3 initial detector
**Goal:** Accept the human's authorization to proceed past Gate 2 with the audit caveat intact and build the first learned detector as soon as possible.
**Done:** Added `LSTMClassifier` and `scripts/train_v3_lstm.py`, a CPU binary LSTM harness using the balanced training index, validation macro-F1 checkpoint selection, and realistic-prevalence test metrics. Added a forward/determinism test. Recorded D-034 authorization, registered E-003 before training, and updated ROADMAP/PROJECT_CONTEXT/EXPERIMENT_REGISTRY.
**Ran / verified:** Test-first import test initially failed because `flids.models` did not exist; after implementation, focused test passed (1 passed). Initial script `--help` exposed a missing `src/` import path; fixed it and verified `--help` and `py_compile`. Full suite: **282 passed in 14.90s**. `git diff --check` passed. E-003 ran on CPU for seeds 0-4 against `data/sequences_v3/seed_42_phase2`; configs record Torch and other library versions. Results are in ignored `results/E-003/binary_lstm/seed*/`.
**NOT verified:** No HDD archive contents beyond one embedded README/tar listing were ingested; no compatibility, coverage, or split-isolation validation for `data/hdd_data`; no GRU/CNN/Transformer, classical baseline, multiclass detector, or federated work. No operational ADS-B performance claim is supported. The low score has not been diagnosed by attack family or validation-only error analysis.
**Results:** From the five per-seed `metrics.json` files: test ROC-AUC mean 0.5742, 95% t-interval half-width 0.0276; PR-AUC 0.00443 ± 0.00048; macro-F1 at threshold 0.5 0.4380 ± 0.0542; normal FPR at threshold 0.5 0.2245 ± 0.1654. Per seed: ROC-AUC 0.5708, 0.5440, 0.5675, 0.6041, 0.5846. Test prevalence is 117/37,683 non-ambiguous windows. These are pipeline-validation results; they do not meet the requested 0.9 ROC-AUC.
**Problems / surprises:** Test PR-AUC is close to the 0.0031 attack prevalence, and validation selected checkpoints between epochs 1 and 10. The detector discriminates weakly on this split despite balanced training. The four-day archive set is 90 hourly `.csv.tar` bundles (~12 GiB) containing nested hourly gzip data, rather than a prepared dataset.
**Decisions made:** D-034: human authorized Gate 2 progression while retaining the failed shortcut-audit caveat. E-003 was pre-registered; no test-based tuning was performed.
**Next steps:** (1) Inspect E-003 validation predictions and per-family/stratum performance without using test results for selection. (2) Build a new read-only-source ingestion path for the HDD tar/gzip archives and validate schemas, coverage, and aircraft-level split handling. (3) Rebuild a separately versioned attack/sequence dataset from that source, then pre-register and run a multi-seed detector experiment.
**Questions for human:** None; progression and use of `data/hdd_data` are authorized. The 0.9 ROC-AUC target remains an unverified goal, not a guarantee.

### 2026-10-23 — Session 4o follow-up — Codex — Checkpoint preservation
**Goal:** Ensure the trained E-003 detector is reusable, not only represented by prediction and metric files.
**Done:** Added `save_checkpoint` for portable CPU model state dicts and wired the training harness to write `model_state.pt`. Added a checkpoint round-trip test. Preserved the original five-seed E-003 results and ran seed 0 again into a new `seed0_checkpointed/` directory.
**Ran / verified:** Checkpoint test-first failed on missing `save_checkpoint`, then focused tests passed (2 passed); full suite passed (**283 passed in 15.17s**). The checkpoint exists (28,293 bytes), loads into the model, and the repeated run's metrics JSON is exactly equal to original seed 0. The five-seed aggregate is unchanged.
**NOT verified:** No additional seeds were checkpointed, and the HDD archives remain unprocessed. The stored weights are a pipeline-validation artifact, not a production detector.
**Results:** E-003 metrics unchanged; checkpoint path is `results/E-003/binary_lstm/seed0_checkpointed/model_state.pt` (ignored, not committed).
**Problems / surprises:** The initial harness had omitted trained weights, which made the run less directly reusable. The correction is additive and preserves the original run directories.
**Decisions made:** None beyond D-034; checkpointing is an implementation detail.
**Next steps:** (1) Perform validation-only per-family error review. (2) Integrate HDD data into new versioned cleaned/attack/sequence outputs. (3) Continue Phase 3 model comparisons with experiments registered before runs.
**Questions for human:** None.

### 2026-10-23 — Session 4p — Codex — Phase 3 HDD/model plan and docs
**Goal:** Continue with the recommended research workflow, bring the project docs into agreement, and explain the data-to-attacks-to-models pipeline.
**Done:** Added `docs/phase3_hdd_model_plan.md` with staged HDD ingestion, cadence gate, aircraft-first split, synthetic episode injection/provenance, sequence/preprocessing controls, centralized model comparisons, and later FL framing. Rewrote the current snapshot and handoff; updated ROADMAP, README, LIMITATIONS, attack methodology/design status; appended D-035 and this entry. D-035 records the plan and the unresolved cadence decision without claiming any experiment or data processing occurred.
**Ran / verified:** Confirmed branch `phase1-generation` and clean worktree before edits. Read-only archive inventory via PowerShell: 90 `.csv.tar` files, 11.962 GiB total; 24 archives each for 2019-11-18, 2019-11-25, 2019-12-09 and 18 for 2019-12-02. No dataset files were opened or changed in this session. No tests were run because changes are documentation-only. `git diff --check` and commit verification are pending at log-edit time.
**NOT verified:** No full archive schema/cadence/row/duplicate/coverage audit, no HDD cleaning, no attack generation, no sequence build, no model training, and no Phase 4/5 work. A sampled README's ~1-Hz cadence is not a measurement of actual rows.
**Results:** No experiment run; no new metrics. Existing E-003 remains the latest model result (pipeline validation only).
**Problems / surprises:** The archive set is 90 hourly bundles on four weekly dates, not four contiguous full days. The likely cadence differs by about an order of magnitude from the existing attack/window assumptions, so reuse without an explicit cadence decision could change attack durations and window meaning.
**Decisions made:** D-035 records the staged approach and states that the cadence must be audited before selecting time-based semantics or deterministic resampling. No scientific parameter or attack behavior was changed.
**Next steps:** (1) Run the planned read-only all-archive schema/cadence/coverage audit and save a small report outside immutable paths. (2) Based on measured cadence, propose and test the resampling/time-semantics choice before any HDD attack generation. (3) Pre-register any experiment before running it and keep centralized model validation separate from later FL gates.
**Questions for human:** None for the documented next step; pause before any material change to approved attack semantics or any gate transition.
