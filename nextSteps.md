# NEXT_STEPS.md — staged plan to get FL-IDS back on its intended path

**Written:** 2026-10-26. **Branch:** `phase1-generation`.
**How to use:** an agent (Claude Code, Codex, etc.) reads `AGENTS.md`, `docs/MASTER_CONTEXT.md` (if present), `docs/PROJECT_CONTEXT.md`, the last 3 `docs/PROGRESS_LOG.md` entries, and **this file**; finds the **first unchecked stage** below; does only that stage; ticks its box with the commit hash; stops where the stage says STOP. Do not skip ahead.

---

## 0. Why this file exists (read once)

The project built Phase 2 and Phase 3 on the **seed-42 pilot** (7 families, moderate tier, τ=0.005, 120 s episodes, 263 accepted episodes total) before the Phase 1 fixes, Gate 1b, quota datasets, and the data-source decision were done. Consequences:

- **E-002 (shortcut audit) and E-003 (binary LSTM) are PILOT-DERIVED.** Test ROC-AUC 0.574 on 117 test attack windows is uninterpretable. They must not be cited as results or used to tune anything.
- Phase 2 features are absolute standardized values plus missing flags. They have **no delta/residual features**, so most attacks are nearly invisible to any model (a 2.5 km shift ≈ 0.0013σ of the latitude scale).
- Shortcut audit failed (per-feature summaries ROC-AUC ≈ 0.60) and was overridden (D-034). Controls were matched only on missing-cell count, not on the eligibility predicate or speed band, and the audit has no confidence intervals.
- Track A (novelty detection, the primary track per D-006) has not been started.
- Phase 1 fixes still open: `speed_band="unknown"`, `freeze_anchor_source_row_id=null`, `onground` NaN silently coerced to `True`, no quota mode, no content validation of generated data, Gate 1b never run, tiers approved without recalibration under the real ramp (first step = 0.25 × magnitude).
- A much larger source (`data/hdd_data`, 90 hourly archives, 4 weekly dates, ~12 GiB, README suggests ~1 Hz) exists. The attack framework assumes 10 s rows. **Decide the source before generating the real datasets.**

## 1. Binding rules (also in AGENTS.md)

1. Never modify or delete `data/`, `results/`, or any existing run directory (including `stage1_seed_42*`, `sequences_v3/*`). New outputs go to new versioned directories.
2. Tests first; small diffs; one commit per stage; **commit before building any dataset** (writers and builders must refuse a dirty tree; `sequences_v3` builder currently does not — fix in S1).
3. Never invent numbers. Every number in docs comes from a result file. Never claim something ran unless it ran.
4. Commands expected to take >5 minutes (data builds, generation, training, calibration on the real table): **print the exact command and WAIT** for the human to run it and paste results.
5. No test-set tuning. No chasing a target metric (the "0.9 ROC-AUC" idea is not a goal). Thresholds come from validation normal scores.
6. Register every experiment (E-###) **before** running it, using the next free number. Use the next free D-number for decisions; never edit old entries — add superseding entries.
7. Do not open `docs/calibration_v3_stage1.json` whole (huge); query with short Python.
8. Stop at every STOP and report in ≤15 lines: what changed, what ran (with outputs), what did NOT run, what you need from the human.

## 2. Stages (tick when done: `- [x] S1 (commit abc1234)`)

### Stage 0 — Docs, supersession, hygiene
- [x] **S0** (commit cced56f)
1. Add `.claude/` to `.gitignore`.
2. New decision (next free D-number): `stage1_seed_42_retry4` is a **pilot** (family list, tier moderate, τ=0.005, 120 s, baro_only, 1 seed, 263 accepted episodes); supersede D-032's Gate 1 acceptance (history kept); Phase 2/3 outputs built on it are **pilot-derived**.
3. Register the pilot run as an experiment from its `manifest.json` only (counts, accepted by family, rejections, commit hash, `git_dirty`). Mark E-002 and E-003 "PILOT-DERIVED — not results".
4. New decision: D-028 supersedes the Eq. 10 portion of D-004 (τ is a per-eligible-segment Bernoulli probability, **not** Li et al.'s density/strength η). Paper wording must say so.
5. Extend `docs/LIMITATIONS.md`: two-hour 2017 source (until HDD decision), decoded state vectors not raw ADS-B, synthetic data-layer attacks, τ ≠ Eq. 10, descriptive-only plausibility, no RF/bit-level/multilateration effects, geoaltitude glitches, antimeridian-unaware medians, pilot-scale results, shortcut audit not passed.
6. Tidy `docs/ROADMAP.md` (tick what is built, remove stale items) and `docs/PROJECT_CONTEXT.md`; mark `docs/CHAT_HANDOFF.md` superseded by `docs/MASTER_CONTEXT.md`; add this file to the context reading list.
7. `tests/test_phase3_lstm.py`: use `pytest.importorskip("torch")`.
**STOP.**

### Stage 1 — Code fixes (source-independent)
- [x] **S1** (commit df2f7ba) (tests first; say which golden digests intentionally change)
1. `episodes.speed_band` = `kinematics.speed_band` of the **median velocity** over the episode rows ("unknown" only if all missing). `anchor_from_offsets` also returns the anchor offset; `episodes.freeze_anchor_source_row_id` = global `source_row_id` of the anchor (null for non-freeze).
2. `onground`: write `scripts/check_onground_nulls.py` (read-only, do NOT run; null counts per split on the cleaned table). Make `onground` nullable in `schemas.py`; null → ineligible for every family; carry nulls to outputs; remove the `bool()` coercion in the assembler. NaN-fixture test.
3. `OverlaySpec` validation: reject specs whose `n_rows` cannot yield ≥5 effective rows (use `ramps.effective_row_count` with realized multipliers); includes gradual at 120 s.
4. Run plans: `configs/run_plans/*.yaml` listing overlays (family, tier, duration_seconds, onset_mode ∈ {linear_mix, abrupt}, altitude_variant, tau **or** quota targets, episodes_per_segment). `scripts/generate_attack_v3.py --plan PLAN` (keep old flags). Support `onset_mode` end to end. The CLI must no longer silently produce a pilot: require `--plan` or explicit family/tier/tau/duration, and print the resolved plan.
5. Manifest additions: total elapsed seconds; per-chunk seconds (min/median/p95/max); resolved plan; window counts by label × stratum × family × split; requested vs realized τ per overlay and split; per-overlay episode/aircraft/window counts. `--progress-log PATH`.
6. Naming: make `dataset_mode`/`selection_method` consistent ("equal-probability Bernoulli per eligible segment, unstratified") via a new decision.
7. `scripts/build_sequences_*.py` and the sequence builder must refuse a dirty git tree and record the commit hash.
**STOP.**

### Stage 2 — Quota mode and dataset plan (still source-independent)
- [x] **S2** (commit 09ddd23)
1. Ranked quota selection, two passes, deterministic, chunk-independent: pass 1 computes eligibility and the overlay-keyed `selection_u` for every segment (no episode building); then per overlay and split take the lowest-`u` eligible segments until BOTH the episode target and the unique-aircraft target are met; pass 2 builds episodes only for selected segments. Honor `fail_on_capacity_shortfall` (raise with the per-cell shortfall table). Keep Bernoulli mode as the realistic-prevalence mode. Manifest records requested/feasible/realized per cell.
2. `scripts/capacity_study.py` (read-only, do NOT run): per candidate overlay (family × tier/duration × onset_mode) and split: eligible segments, eligible starts, unique aircraft, and how many overlays fit in a merged dataset at one overlay per segment.
3. Propose (as a PROPOSED decision) a **dataset plan** with three kinds: (A) per-cell evaluation overlays, one overlay per run, quota-filled, for per-family/tier/duration recall incl. boundary vs interior-only (long episodes 600/900 s for gradual/constant/freeze); (B) a mixed realistic-prevalence set (all families, small τ); (C) a mixed Track B training set. Do not generate anything.
**STOP** for human approval of the dataset plan.

### Stage 3 — HDD source audit (read-only)
- [x] **S3** (commit 600ba2f)
`scripts/audit_hdd_source.py [--max-archives N] [--out results/hdd_audit_v1]`: streams each `*.csv.tar` without permanent extraction, resumable per archive, memory-bounded; **never modifies `data/hdd_data`**. Write per-archive JSON + a summary JSON:
1. Schema: README (first 2 KB), columns/dtypes, differences from the existing source (needs: time, icao24, lat, lon, velocity, heading, vertrate, onground, baroaltitude, geoaltitude, lastcontact).
2. Time: min/max per archive, covered dates/hours, gaps, rows per hour.
3. Cadence per `icao24` track: consecutive-`dt` quantiles (p01/p05/p25/p50/p75/p95/p99), share exactly 1 s and exactly 10 s, share of tracks with gaps >30 s.
4. Aircraft: unique `icao24` per archive/date; recurrence across hours and across the four dates (split-leakage risk).
5. Quality: missingness per column, `onground` share, duplicates on (icao24, time), sort order, velocity/heading units and ranges, lat/lon box and 5° cell coverage, `lastcontact`−`time`.
6. Compute budget: rows/hour and extrapolated total after **candidate** deterministic resampling to 10 s (decimate at `time % 10 == 0` vs nearest sample) — documented, not implemented.
Write `docs/hdd_audit_report_template.md` listing the human decisions the results require (split by aircraft vs by date; resampling rule; assembler unchanged or not; time-of-day/day-of-week coverage). Tests on tiny synthetic fixtures for pure helpers. Do NOT process, resample, or attack HDD data.
**STOP.** Human runs the script and pastes `results/hdd_audit_v1/summary.json`.

### Stage 4 — HUMAN GATE (agent: do nothing, wait)
- [x] **S4** (D-041) Human decided: HDD primary source, no resampling (data is already ~10 s), global hashed-`icao24` split; D-039 plan approved at D-040. Audit: `results/hdd_audit_v1/summary.json` (90 archives, 207M rows, 79,755 aircraft, 4 dates).

### Stage 5 — Source preparation (only after S4 approval)
- [x] **S5** (commit 7a44712)
If HDD is chosen: `scripts/build_hdd_dataset.py` writes a **new versioned** `data/processed/<name>/` in exactly the schema and conventions of `opensky_clean_v1` (same columns incl. `*_missing`, `heading_sin/cos`, `contact_lag_*`, `segment_id` split at >30 s gaps, `time` int64 epoch seconds), after the approved deterministic resampling to 10 s; processed per hour in chunks; reuse functions from `scripts/build_dataset.py` rather than rewriting. A **global aircraft-level split** (hash of `icao24` with a fixed seed so an aircraft is in one split across all hours and dates) saved as a new split file; never reuse `split_aircraft.json` for new aircraft. Provide `scripts/validate_clean_source.py` (natural-key uniqueness, sorted order, dt distribution = 10 s, schema equals `opensky_clean_v1`, fingerprints, split coverage and disjointness, rows/aircraft/segments/missingness table vs the old source) and a content fingerprint. Human runs the builder and validator.
**STOP.**

### Stage 6 — Gate 1b calibration on the chosen source
- [x] **S6** (commit PENDING)
`scripts/gate1b_calibration.py` (read-only; human runs; output `results/gate1b_calibration_v2.json`, never overwrite the old JSON); thresholds from **train aircraft only**:
1. Oracle boundary recall vs horizontal magnitude (500–16,000 m), **abrupt and the real ramp (first step 0.25 × magnitude)**, per speed band; propose tiers at ≈10/30/60/90% for fast bands; gross control abrupt.
2. Integrated-residual oracle (k = 5, 10, 29): position change over k steps minus Σ v·dt, train-only p95 per band and k; recall for gradual (600/900 s), freeze, constant offset (interior and boundary).
3. Partial-replay oracle for the boundary pair and interior pairs separately.
4. Altitude oracle (`baro_only`, `baro_plus_geo`) per tier using vertical-rate-band p95 of the altitude residual; separate or exclude the 15+ m/s band.
5. Oracle FPR on maneuver-matched controls; residual quantiles per speed band and `dt`.
6. Per-overlay capacity per split/speed band/unique aircraft on the chosen source.
Print a tier proposal; do not change the YAML. **STOP.** Human + Claude review; parameters re-approved in a new decision before generation.

### Stage 7 — Generation and content validation
- [ ] **S7**
1. `scripts/validate_generated_dataset.py RUN_DIR` (write + test on fixtures first; human runs on real output): schema/footers/counts/SHA-256 equal manifest; `attacked_rows` maps 1:1 to source by `source_row_id`; `orig_*` equals source, metadata equals source, rows outside accepted episodes have `mod == orig`; every attack row lies in an accepted episode inside one (icao24, segment_id); episodes don't overlap and keep the 600 s gap; every episode row eligible (recompute with `eligibility.py`); ramp multipliers/positions equal `ramps.py`; effective rows ≥5; no-op guard satisfied; injected displacement equals multiplier × parameter (constant/gradual); replay values equal blended ORIGINAL source rows with delays within tolerance; freeze rows hold the stored anchor; windows recomputed from step labels equal the stored table; no window overlaps two episodes; `overlay_selections`/`segments`/`episodes` mutually consistent; split membership matches the split file; requested vs realized τ with a binomial interval; per-family displacement quantiles. JSON pass/fail report.
2. Human runs generation per the approved plan, one run at a time with `--progress-log`, from a **clean committed tree**, each registered as an E-### first. Then `validate_generated_dataset.py` on each; Claude reviews; Gate 1 is re-decided on the real datasets.
**STOP** after each generation + validation.

### Stage 8 — Phase 2 rebuild (new sequence datasets; never on the pilot)
- [ ] **S8**
1. **Feature set v4**, computed per segment at row level before windowing, with an explicit mask for every undefined value (segment start, gap >30 s, missing inputs):
   - absolute channels as now (lat, lon, velocity, heading sin/cos, vertrate, baro, geo) but with **last-observation-carried-forward within the segment** (fallback to train mean only at the start of a segment) plus masks, instead of global-mean fill;
   - **delta/residual channels**: step north/east metres (`kinematics` convention), `dt`, position-vs-`v·dt` residual (earlier row's velocity/heading, as in the calibration), implied speed minus reported speed, baro and geo altitude residual (`Δalt − vertrate·dt`), wrapped Δheading;
   - scale with train-only robust/signed-log scaling (heavy tails); scaler fit on **normal** train windows only for Track A.
2. **Eligibility-matched controls:** normal windows for audits and matched evaluation satisfy the same eligibility predicate as the attacks and are matched on speed band and missing count. Report FPR on matched controls **and** on the full unfiltered normal population.
3. **Shortcut audit v2** (missingness, window position, absolute-summary, delta-only, on-ground/stale, contact-lag) with **aircraft-cluster bootstrap 95% CIs**. Write a PROPOSED decision defining the near-chance criterion **before running** and wait for approval. A failure blocks Phase 3 (no override without a recorded human decision).
4. Track A training windows contain **zero attacked rows and no ambiguous windows**; per-step and per-window labels, strata (boundary/interior_only), binary + multiclass labels.
5. New output dir; builder refuses dirty tree; manifest with hashes.
**STOP.** Gate 2 is a separate human review.

### Stage 9 — Phase 3 baselines (Track A first)
- [ ] **S9** (register E-### first; ≥5 seeds; CIs by aircraft-cluster bootstrap; no test-set tuning)
1. **Track A (headline): LSTM autoencoder** trained on normal windows only; loss masked by the missing masks; score = masked reconstruction error; threshold = validation **normal** score at 1% FPR (also 5%); report recall at fixed FPR per family/tier/stratum, ROC-AUC/PR-AUC, FPR on matched and full normal populations, detection latency from per-step labels. Add trivial references: oracle residual detector and Isolation Forest on delta-feature summaries.
2. Then 1D-CNN autoencoder (and optionally a small Transformer).
3. **Track B (upper-bound reference):** LSTM/GRU/CNN classifiers on the identical splits and evaluation sets; LR/RF on engineered features.
4. Model selection on validation only (normal validation loss for Track A). Never report at a fixed 0.5 threshold as an operating point.
**STOP** at each model family for review. Phases 4–8 (client partitioning, FL, robustness, evaluation, paper) follow only after Gate 3; see `docs/MASTER_CONTEXT.md` §7.

---

## 3. Notes for the human

- **Suggested models/effort:** S1, S2, S5, S7(validator), S8 touch splits/labels/eligibility/seeding → Sonnet at medium effort or `opusplan`; S0, S3, tests/docs boilerplate → a cheaper model (Haiku or DeepSeek V4 Flash via Claude Code), reviewed by Claude chat.
- **After each stage:** `pytest -q`, `git push`, tell Claude (chat) — it clones the branch and reviews with brute-force references before you approve the next stage.
- **Human-run long jobs** (always in the activated venv, one command at a time, `2>&1 | Tee-Object -FilePath logs\<name>.log`): `check_onground_nulls.py`, `capacity_study.py`, `audit_hdd_source.py`, builders, `gate1b_calibration.py`, generation, validators, training.
- **Token budget:** run one stage per session, `/clear` between stages, never let the agent read huge JSON/data files, and keep this file as the only plan the agent needs.
- **Paper hygiene:** do a real literature search (Scholar, IEEE Xplore, Scopus, arXiv) before any novelty claim; keep `docs/LIMITATIONS.md` current; nothing from E-002/E-003 enters the paper.