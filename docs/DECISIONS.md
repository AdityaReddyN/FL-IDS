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
