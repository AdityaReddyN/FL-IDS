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
