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

### D-004 — Attack proportion (PROPOSED, UNAPPROVED; 2026-10-16)
**Context:** Li et al. Eq. 10 provides a density/strength-aware attack proportion;
the paper's 0.05% flight share is too small for this dataset.
**Options considered:** Paper's fixed 0.05% share; a fixed larger share; Eq. 10 sweep.
**Decision:** Proposed: use Eq. 10 with tau swept over {0.005, 0.01, 0.05, 0.1}.
**Why:** Preserves the paper's parameterisation while providing enough examples.
**Type:** implementation choice
**Consequences / risks:** Requires human approval and an explicit documented deviation.

### D-005 — Amplitude and stealth (PROPOSED, UNAPPROVED; 2026-10-16)
**Context:** The paper supplies Eqs. 11-13 but not all numeric constants.
**Decision:** Proposed: derive amplitudes from historical per-attribute statistics,
state the Eq. 11 interpretation, and define three stealth tiers via Gamma/zeta;
add Eq. 12 Gaussian noise.
**Why:** Uses available paper structure without inventing unspecified constants.
**Type:** implementation choice
**Consequences / risks:** Requires human approval and calibration validation.

### D-006 — Two detection tracks (PROPOSED, UNAPPROVED; 2026-10-16)
**Context:** The paper treats labels as evaluation-only, while the current v2 baseline is supervised.
**Decision:** Proposed: evaluate novelty/semi-supervised detection trained on mostly normal
data alongside supervised multiclass detection as an upper bound; include the former in headline FL results.
**Why:** Better matches the paper's stated label usage.
**Type:** implementation choice
**Consequences / risks:** Requires human approval and expands Phase 3/5 scope.

### D-007 — Rename v2 replay label (PROPOSED, UNAPPROVED; 2026-10-16)
**Context:** v2 `replay_freeze_sim` is a fixed-value manipulation, not delayed replay under Eq. 8.
**Decision:** Proposed: retain v2 labels for baseline provenance but name the Phase 1 class
accurately and add true 300 s delayed replay on lat/lon/baroaltitude at minimum.
**Why:** Avoids conflating distinct paper attack families.
**Type:** paper-grounded
**Consequences / risks:** Requires human approval; no mutation of v2 artifacts.

### D-008 — Enable ghost and DoS scope (PROPOSED, UNAPPROVED; 2026-10-16)
**Context:** Extracted details specify ghost and DoS variants absent from the prior accessible text.
**Decision:** Proposed: implement ghost variants and DoS period/whole/cycle variants;
keep ghosts with their source split and reserve synthetic ICAO IDs. Audit DoS missingness shortcuts.
**Why:** The source now gives enough high-level procedure to implement transparently.
**Type:** implementation choice
**Consequences / risks:** Requires human approval; physical plausibility and shortcut risks remain.

### D-009 — Episode-level injection (PROPOSED, UNAPPROVED; 2026-10-16)
**Context:** Paper attacks occur in attack windows within flights, while reference code also uses whole-flight attacks.
**Decision:** Proposed: support attack episodes within flights as well as whole-flight episodes.
**Why:** Preserves temporal attack structure and enables spanning future windows.
**Type:** paper-grounded
**Consequences / risks:** Requires human approval and episode provenance.
