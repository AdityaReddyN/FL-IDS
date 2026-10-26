# FL-IDS handoff

> **SUPERSEDED (2026-10-26, D-036).** This file is kept for history only. The
> live navigation aid is `docs/MASTER_CONTEXT.md` (human-maintained) and the
> staged plan in `nextSteps.md`. Content below predates the pilot reclassification
> and must not be treated as current state or as gate authorization.

**Snapshot:** 2026-10-23, Session 4p. This is a navigation aid, not permission
to cross a gate. Re-read `AGENTS.md`, current docs, Git branch/status, and live
configs at the start of new work.

## Current verified state

- Expected branch: `phase1-generation` (verify). Phase 1 seed-42 dataset passed
  Gate 1 (D-032); Phase 2 sequence construction is complete. The human
  authorized Phase 3 while preserving E-002's failed near-chance summary
  shortcut criterion (D-034). Do not describe that audit as passed.
- E-003: five-seed binary LSTM on the two-hour v3 sequences; mean test ROC-AUC
  0.5742 (95% t-interval half-width 0.0276), PR-AUC 0.00443,
  macro-F1@0.5 0.4380, normal FPR@0.5 0.2245. Pipeline validation only; no
  0.9 ROC-AUC guarantee. Seed-0 checkpoint is in ignored results.
- `data/hdd_data`: 90 `.csv.tar` archives / 11.962 GiB, four weekly dates,
  including 18 hourly archives for 2019-12-02 and 24 for each other date. One
  sampled CSV header is OpenSky decoded-state-vector style; its README describes
  about 1 Hz. Actual all-archive cadence/schema/coverage are unverified.
- No HDD processing, attacks, windows, or training have been run. Existing
  attack/window semantics assume roughly 10-second rows; first audit cadence.
- No FL code or actual receiver IDs exist. Geographic-grid clients would be
  simulated geographic assignments.

## Next work

Follow `docs/phase3_hdd_model_plan.md` in order: read-only archive audit;
streaming cleaner into a new versioned output; explicit cadence decision and
tests; aircraft-first split; synthetic episode attacks with provenance;
within-segment/split windows and train-only preprocessing; shortcut controls;
then registered multi-seed centralized model comparisons. The planned models
are LR/RF over engineered window summaries and LSTM, GRU, temporal 1D-CNN, and
small Transformer. Binary selection is validation PR-AUC; multiclass selection
is validation macro-F1. Thresholds for fixed FPR are calibrated on validation
normal windows. Locked test is evaluated once.

Before running an experiment, register it as planned in
`docs/EXPERIMENT_REGISTRY.md`; record result values only from files. Update
DECISIONS/ROADMAP/PROJECT_CONTEXT/PROGRESS_LOG as relevant and commit. Never
modify immutable data or `results/centralized_lstm/`, commit data/weights, tune
on test, or push/merge. Stop at the Phase 3 gate before later phases unless
human authorization explicitly covers them.

See `docs/PROJECT_CONTEXT.md` for concise current facts and `docs/LIMITATIONS.md`
for validity caveats. The attached `context.docx` is external review material;
its January/February source and reported scores have not been verified here.
