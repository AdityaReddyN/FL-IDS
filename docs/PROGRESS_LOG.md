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
