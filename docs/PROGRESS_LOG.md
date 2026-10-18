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

