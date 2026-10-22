# FL-IDS project handoff for a new chat

**Snapshot date:** 2026-10-22
**Purpose:** Give a new assistant enough project context to resume work without
relying on another chat. This is a navigation aid and current-state summary;
the repository's `AGENTS.md`, `docs/PROJECT_CONTEXT.md`, `docs/ROADMAP.md`,
`docs/DECISIONS.md`, and `docs/PROGRESS_LOG.md` remain authoritative.

## Start here

At the beginning of a new session, read in this order:

1. `AGENTS.md` in full.
2. `docs/PROJECT_CONTEXT.md` and `docs/ROADMAP.md`.
3. The latest five entries of `docs/PROGRESS_LOG.md`.
4. Relevant entries in `docs/DECISIONS.md` and `docs/EXPERIMENT_REGISTRY.md`.
5. For Phase 1, also read `docs/attack_generation_methodology.md`,
   `docs/attack_v3_design.md`, `configs/attack_v3_stage1.yaml`, and relevant
   modules/tests under `src/flids/attacks/` and `tests/`.

Do not treat this handoff as permission to cross a human approval gate. If its
state disagrees with the live config or newer repository docs, verify and follow
the newer source. At this snapshot the current branch is `phase1-generation`,
the latest commit is `61edcca phase1: stage A parameter approval and validation`,
and `git status --short` showed an untracked `.claude/` directory. That directory
was not inspected or modified. Git also warned that `.pytest_cache/` could not be
opened in this environment. Recheck branch and status before any work.

## Mission and scientific framing

The project aims to study federated-learning-based intrusion detection for
ADS-B surveillance data. The pipeline is decoded OpenSky state vectors ->
synthetic row-level attack simulation -> sequence windows -> centralized and
federated detectors. The input is **decoded state-vector data, not raw 112-bit
ADS-B messages**. Attack labels are synthetic; results cannot establish
operational aviation-IDS performance or RF/physical replay fidelity. The source
data is limited to about two hours, so coverage limits any geographic or
non-IID claims.

Exact parts of Li et al. (2020) are not reproducible from accessible text. Mark
all unverified mappings and numeric choices as implementation choices; never
invent paper details. Investigate suspiciously high metrics (>0.99 F1) for
leakage or shortcuts. Split by aircraft before windows, fit preprocessing on
training data only, and never tune on test data.

## Project state

- Phase 0 is complete and Gate 0 was approved.
- Phase 1 attack primitives and a pure, in-memory overlay assembler exist.
- Session 4a Stage A is complete: approval-sheet generation and a read-only
  real-data assembler diagnostic were run. This was pipeline validation, not a
  scientific result, and no parameters were tuned.
- The human approved Draft 4 parameter values in Session 4d (D-029), and the
  live config is now `status: approved`.
- Stage B is complete: multi-overlay chunked assembly/writer, per-overlay
  selection evidence, lexicographic conflict resolution, manifest/config,
  plausibility report, multi-family CLI/dry-run, and SVG plot helper. D-031
  corrects nullable episode IDs and records the eight-table format. Synthetic
  tests pass. Seed-42 generation was attempted but manually stopped after
  partial Parquet row groups were written without a manifest/config/report.
  `data/attack_generation_v3/stage1_seed_42/` is incomplete and must not be
  treated as a dataset; retry to a new run directory.
- Gate 1 (review of manifest, plausibility report, and plots) is not passed.
  Phase 2 and all later phases remain unstarted; do not mark Gate 2 or Gate 3.
- Stage C seed-42 generation is explicitly authorized after Stage B review. It
  still requires a clean committed tree; `.claude/` was handled by the human.
  After generation, stop for Gate 1 review; do not start Phase 2 before approval.

## Data and prior baseline

Measured cleaned-table facts recorded in `PROJECT_CONTEXT.md`:

- `data/processed/opensky_clean_v1.parquet`: 2,970,285 rows, 14,279 aircraft,
  21,389 segments; 2017-06-05 00:00:00–01:59:50 UTC.
- Latitude range [-39.502227, 65.120389], longitude range
  [-155.835677, 175.842876]. Segment gaps exceed 30 seconds.
- Missingness is substantial: lat/lon 30.32%, velocity/heading 32.83%,
  vertical rate 29.78%, barometric altitude 9.79%, geo altitude 38.98%.
- `data/sequences_v2/` is immutable and shortcut-prone. It has 30-row windows,
  stride 10, aircraft 70/15/15 split, train-only preprocessing, five balanced
  classes, and ad hoc v2 attacks.
- E-001 reproduces the seed-42 centralized LSTM: test accuracy 0.664533,
  macro-F1 0.648890, normal-window FPR 0.726333; best validation macro-F1
  0.652434 at epoch 9. This is a single-seed, v2 baseline, not a scientific
  Phase 3 result.
- v2 diagnostic: normal-data FPR 72.63%, position-spoof recall 28.37%.
  Suspected shortcuts and causal hypotheses are documented in
  `PROJECT_CONTEXT.md`; they are not established causal findings.

Never modify immutable `data/raw/`, `data/processed/opensky_clean_v1.parquet`,
`data/sequences/`, `data/sequences_v2/`, or `results/centralized_lstm/`. Data
and model weights must not be committed.

## Phase 1 implementation map

Under `src/flids/attacks/`:

- `config.py`, `keys.py`, `fingerprint.py`, `seeding.py`, `splits.py`,
  `schemas.py`, `manifest.py`: config approval, natural keys, fingerprints,
  deterministic RNG, fixed split access, table validators, and manifest
  scaffolding.
- `kinematics.py`, `eligibility.py`, `placement.py`: movement/eligibility,
  replay source lookup, deterministic episode placement and spacing.
- `ramps.py`, `manipulation.py`, `replay.py`, `freeze.py`,
  `detectability.py`: attack multipliers, horizontal/altitude manipulation,
  delayed replay, freeze, and reporting quantities.
- `episode.py`, `windows.py`, `assembler.py`: pure in-memory episode building,
  v2-anchored window labels/strata, and overlay assembly.
- Tests are synthetic and live in `tests/`. The assembler preserves every input
  row, uses natural keys, validates output tables, and handles NaN feature
  values. Its output is in memory only.

No library code may read YAML. Do not modify `src/flids/attacks/` during a task
that explicitly excludes it. Tests first; keep diffs small.

## Decisions that govern the next work

- **D-020:** Design principles approved: truth/labels decoupled from
  detectability; ungated shared eligibility for primary construction;
  detectability is post-hoc strata; 600/900-second episodes included; train-only
  calibration thresholds. Numeric values below are still provisional.
- **D-021:** eligibility, replay lookup, actual-span filter, placement
  conventions; required fields and 0.8/1.25 span factors provisional.
- **D-022–D-024:** ramp/composition, gradual deviation, replay/freeze, effective
  row count, episode rejection behavior, 30-row/stride-10 window labels, and
  provisional no-op thresholds. Tier values and some thresholds remain
  unapproved.
- **D-025–D-027:** pure in-memory assembler, deterministic IDs and RNG streams,
  global replay provenance, separate placement RNG, strict provenance JSON,
  nullable feature columns and contact lag, finite-only cell medians.
- **D-028 (human-approved):** overlay key is included in segment-selection
  entropy; merged data allow at most one overlay per segment; conflict order is
  lexicographically ascending overlay key and conflicts are recorded as
  `overlay_conflict`. `tau` is Bernoulli eligible-segment selection
  probability, not paper Eq. 10 eta; column is `tau_requested`.
- `selection_method="uniform_per_subairspace"`, `speed_band="unknown"`, and
  `freeze_anchor_source_row_id=None` have known limitations documented in D-026.
  Do not silently rename schema fields or invent metadata conventions.

## Stage A observed validation (not scientific results)

From the latest Stage A progress entry:

- Baseline full suite before D-028 edits: 253 passed; focused updated tests:
  47 passed. Do not assume a full-suite run after those edits unless verified.
- Approval sheet printed proposed tiers, sigmas, kappa, altitude shifts,
  quotas, required fields, span/no-op thresholds, durations and ramp settings.
- Read-only check used 300 seeded random train segments per family at tau=0.2.
  No schema/NaN error. Selection fractions: constant 0.2222, Gaussian 0.2667,
  gradual 0.2000, altitude 0.2044, partial replay 0.1714, full replay 0.1881,
  freeze 0.2370. These are small-sample pipeline checks, not results.
- Rejections: gradual 27 `insufficient_effective_rows`; freeze 2
  `no_freeze_anchor`, 5 `no_measurable_change`; none reported for the other
  four families. Per-family peak Python memory ~116.1–124.6 MB.
- Gaussian runtime was 126.45 seconds per 100 sampled segments (extrapolated
  ~27,046 seconds over all 21,389); other families ~10.42–11.56 seconds per
  100. Gradual 120-second episodes have only four effective rows and were
  rejected under the five-effective-row rule. No tuning was done.

## Exact gates and permitted next steps

### Stage A human approval — complete (D-029)

The human approved the Draft 4 values listed by `scripts/make_approval_sheet.py`;
`configs/attack_v3_stage1.yaml` is now `approved`. Do not change the approved
values without a new human decision.

### Stage B — current implementation status

The current work adds the single-overlay pieces above. The multi-overlay
selection/conflict merge is still unresolved because the specified `segments`
schema has one selection draw while each overlay has a distinct stream and
eligibility mask. D-030 records the issue. Keep the legacy golden output until
the human decides whether its episode-ID rounding bug may be corrected.

### Stage C — human gate after Stage B review

Generation to `data/attack_generation_v3/<run_id>/` is permitted only after the
human reviews completed Stage B, resolves D-030, and explicitly says “go”, from a clean committed tree.
Generate seed 42 first. Do not generate later seeds until review. Never write to
immutable paths, never commit data, and do not push or merge.

## Remaining project roadmap

- **Phase 1:** Stage A values approved; finish Stage B's merge/ID decisions,
  obtain Stage B review and explicit Stage C go, then generate and pass Gate 1.
- **Phase 2:** build v3 sequence windows, split by aircraft before windowing,
  train-only preprocessing, realistic and balanced sets, leakage/shortcut
  audits, then Gate 2.
- **Phase 3:** centralized baselines only after Gate 2; Gate 3 remains
  unapproved. A prior Phase 3 infrastructure request on a different branch
  described v2-only outputs as pipeline validation and explicitly prohibited
  ticking Gate 3; it does not override the current Phase 1 branch/gates.
- **Phases 4–8:** client partitioning, FL, robustness/privacy, evaluation, and
  paper support are future work. No FL code exists yet; v2 client IDs are IID
  placeholders.

## Mandatory working rules

Read `AGENTS.md` every session. Keep records in `docs/`; append decisions and
progress rather than deleting history. Register experiments as `planned` before
running, and copy results from actual files. Do not run training, real-data
checks, or data generation unless explicitly within the current authorization.
Respect branch requirements and approval gates; never push or merge unless
asked. At each session end, report what changed, ran, passed, and remains
unverified; update progress/roadmap/project context and commit the documentation
with the code it describes.
