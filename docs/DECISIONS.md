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
