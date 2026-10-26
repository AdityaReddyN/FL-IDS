# HDD source audit — report template and human decisions

**Status:** template. Fill in after running `scripts/audit_hdd_source.py` on
`data/hdd_data`. The audit is read-only; it processes, resamples, and attacks
nothing. Paste `results/hdd_audit_v1/summary.json` (and any per-archive JSON of
interest) into Stage S4 for the decisions below. None of these decisions is made
by the agent; they are recorded as new D-numbers when the human decides.

## What the audit produced
- `results/hdd_audit_v1/summary.json` — archives audited, rows total, covered
  dates/hours, rows per archive, aircraft recurrence across hours and across
  dates, and any schema mismatch.
- `results/hdd_audit_v1/<archive>.csv.tar.json` — per archive: schema diff vs
  the cleaned-table contract, README head, time coverage, per-track cadence
  (1 s / 10 s / >30 s shares and dt quantiles), data quality (missingness,
  onground share, duplicate (icao24,time), sort order, velocity/heading ranges,
  lastcontact lag), 5° cell coverage, and a 10 s resampling compute estimate.

## Human decisions for Stage S4 (record each as a new D-number)
1. **Source.** Two-hour 2017 OpenSky, the HDD archives, or both? (Feasibility of
   the D-039 cells depends on this.)
2. **Resampling rule.** If HDD is ~1 Hz: `decimate_mod10` (keep seconds ≡ 0 mod
   10), `nearest_10s` (one row per 10 s bucket), or keep native cadence and adapt
   the assembler. Decide from the cadence quantiles and the compute estimate.
3. **Split strategy.** Split aircraft globally by a hashed `icao24` (so an
   aircraft stays in one split across all hours and dates) vs any date-based
   split. The aircraft-recurrence-across-dates figure quantifies the leakage risk
   of a non-aircraft split.
4. **Assembler compatibility.** Keep the existing ~10 s assembler unchanged (only
   after resampling to 10 s) or adapt episode/window semantics to native cadence.
5. **Coverage adequacy.** Are the covered dates/hours and the lat/lon box + cell
   coverage sufficient for the D-039 per-cell targets, or do some cells become
   descriptive-only / infeasible?

## Not decided here
No magnitudes, tiers, τ, or quota targets; those follow Gate 1b (S6). No data is
generated until S5/S7 on a clean committed tree, each run registered as an E-###
and content-validated.
