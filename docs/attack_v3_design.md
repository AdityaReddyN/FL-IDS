# Attack V3 Design — Decoupled Truth, Detectability Strata, and Long-Episode Feasibility (Draft 4)

**Status:** Approved design basis per D-020 and D-029. D-019 supersedes the effect-gate and window-rule portions of D-011, D-014, and D-018. Dataset generation remains gated on Stage B review and explicit human authorization; this approval does not pass Gate 1.

---

## 1. Scope, Provenance, and Limitations

V3 is a labelled row-level **data-layer simulation** of decoded OpenSky state vectors, not raw ADS-B 112-bit messages. Labels are synthetic and cannot establish operational aviation-IDS performance, RF/physical message replay fidelity, or signal security. Stage 1 encompasses data manipulation and delayed replay; ghost injection and DoS remain deferred to Stage 2 (D-008). The source dataset covers 2017-06-05 00:00:00 to 01:59:50 UTC (~2 hours).

All outputs will record source and modified values, `source_row_id`, the composite natural key `(icao24, segment_id, time, segment_row_offset)`, input schema/content fingerprints, labels, parameters, replay provenance, geographic cell, and candidate acceptance/rejection reasons.

`data/sequences_v2/split_aircraft.json` is reused identically across all injection realizations. Read-only calibration verified coverage of all 14,279 cleaned aircraft with zero missing or extraneous split IDs. Segment random streams derive deterministically from `SHA-256(global_seed | icao24 | segment_id)`. Five injection seeds are required for publishable tables; if fewer are evaluated, an explicit caveat is required. Uncertainty estimation uses aircraft-cluster bootstrap, never row- or window-level shuffling.

---

## 2. Decoupling Truth from Detectability

A core insight from the design review is that conditioning window labels on a residual threshold conflates ontological ground truth (what was attacked) with algorithmic detectability (what triggers a kinematic residual filter). Doing so distorts subtle-tier evaluation and creates artificial selection shortcuts.

### 2.1 Window Labelling Rule (Ground Truth)
An attacked window is defined solely by:
1. **Attacked-row count:** At least 5 attacked rows in the 30-row window.
2. **Minimum effective ramp amplitude:** Overlapping rows must carry effective attack displacement (excluding zero-amplitude ramp endpoints).

The requirement for "effect-qualified rows" is completely removed from the ground truth window labelling rule.

### 2.2 Ambiguous Windows
`ambiguous` is reserved strictly for weak overlap (1 to 4 attacked rows). Ambiguous windows are excluded from Track A novelty training and primary evaluation to avoid boundary edge noise, but are logged in the dataset manifest.

### 2.3 Detectability Reporting Strata
Detectability is reported through post-hoc stratified metrics, NOT used as a selection gate for dataset construction:
- **Boundary stratum:** Windows overlapping the attack onset or offset ramps.
- **Interior-with-residual-qualification stratum:** Windows containing only interior attack rows whose attack-specific effect quantity exceeds the train-split speed-band p95 residual.
- **Interior-without-residual-qualification stratum:** Windows containing interior attack rows where the effect quantity is below the p95 threshold (e.g., subtle constant offsets or low-speed freezes).

---

## 3. Attack-Specific Effect Quantities and Ungated Primary Dataset

The primary dataset is generated using **shared eligibility only (ungated)**. This ensures all tiers (from subtle to gross) are represented with unskewed natural baselines. The gated subset is analyzed and reported separately as a sub-analysis.

For post-hoc detectability stratification, attack-specific effect quantities are compared against the train-split speed-band p95 horizontal residual:
- **Constant deviation:** Onset/offset step displacement. With the default 3-step linear ramp, this is `magnitude / 3.0`.
- **Gradual deviation:** Two complementary metrics:
  - *Per-step drift:* `magnitude / (n - 1)` (e.g., `magnitude / 59` for a 600 s episode).
  - *Cumulative offset:* Total displacement at episode completion (`magnitude`).
- **Gaussian deviation:** Pair residual compared to the speed-band p95 residual, or nominal standard deviation `sigma`.
- **Partial replay:** Current-versus-source kinematic discrepancy (measurable change in speed >= 1.0 m/s, heading >= 1.0°, or vertical rate >= 0.5 m/s, combined with source-to-current residual exceedance across consecutive pairs).
- **Freeze:** Missed natural displacement `velocity * dt` compared to the speed-band p95.

---

## 4. Episode Duration and Interior-Only Window Feasibility

### 4.1 The Short-Episode Bottleneck
With 30-row windows (stride 10) and 3-step ramps (3 onset rows + 3 offset rows = 6 ramp rows), an interior-only window requires that all 30 rows fall strictly within the interior zone:
$$\text{interior zone size} = \text{episode rows} - 2 \times \text{ramp rows} \ge \text{window rows} = 30$$
$$\text{episode rows} \ge 36 \text{ rows} \quad (\approx 360 \text{ seconds at nominal 10 s sampling})$$

In the earlier 90--300 s episodes (9 to 30 rows), the interior zone is at most 24 rows, which is strictly less than 30 rows. Consequently, **exactly zero interior-only windows can exist** in 90--300 s episodes.

### 4.2 Long-Episode Configurations
To support rigorous interior-only evaluation for manipulation and freeze, long-episode settings are introduced alongside the nominal 120 s setting:
- **600 s episodes (60 rows):** Interior zone has 54 rows. Yields a mean of **2.50 interior-only windows** (and 7.85 qualifying windows) per episode.
- **900 s episodes (90 rows):** Interior zone has 84 rows. Yields a mean of **5.50 interior-only windows** (and 10.84 qualifying windows) per episode.

### 4.3 Segment Length Feasibility
Segment duration analysis on the cleaned table (21,389 total segments) confirms abundant capacity for long episodes:
- Segments >= 360 s: **16,171** (75.6% of segments)
- Segments >= 600 s: **12,616** (59.0% of segments)
- Segments >= 900 s: **10,139** (47.4% of segments)
Mean segment length is 1,380.4 s (138.9 rows); median is 810.0 s (82.0 rows).

### 4.4 90 s Freeze Feasibility (Requirement 8)
For a 90 s freeze episode (9 rows at 10 s dt) with 3-step ramps:
- Interior rows = `9 - 2 * 3 = 3 rows`.
- No 30-row window can be interior-only (`3 < 30`).
- Overlapping windows contain at most 9 attacked rows (of which 3 are interior).
- Qualifying windows (>= 5 attacked rows) exist (mean yield 2.74 windows per episode), but they inherently contain ramp boundary rows.
- **Conclusion:** 90 s freeze is evaluable at the boundary+interior stratum only, not the interior-only stratum.

---

## 5. Capacity and Speed-Band Test Reliability

Capacity was calibrated across all splits and speed bands:

### 5.1 Shared Eligibility
- **Train:** 0--50 m/s: 19,330 rows (668 aircraft); 50--100 m/s: 98,315 rows (3,356 aircraft); 100--200 m/s: 258,228 rows (3,915 aircraft); 200+ m/s: 677,844 rows (3,891 aircraft).
- **Test:** 0--50 m/s: 5,115 rows (138 aircraft); 50--100 m/s: 18,113 rows (702 aircraft); 100--200 m/s: 58,898 rows (847 aircraft); 200+ m/s: 143,137 rows (841 aircraft).

### 5.2 Replay Episode Capacity and the Under-100 Aircraft Threshold
In residual-gated partial replay (120 s episodes), test split unique aircraft counts by speed band are:
- **0--50 m/s: 27 aircraft** (633 episode starts, 30 segments) -> **Marked as descriptive only** (< 100 aircraft).
- 50--100 m/s: 233 aircraft (2,982 starts, 237 segments).
- 100--200 m/s: 355 aircraft (5,451 starts, 370 segments).
- 200+ m/s: 200 aircraft (2,764 starts, 207 segments).

Any speed band with fewer than 100 unique test aircraft must be explicitly designated descriptive only in paper tables to prevent statistically unrepresentative generalization claims.

---

## 6. Train-Only Thresholds and Altitude Calibration

### 6.1 Leakage-Free Thresholds
All calibration thresholds are strictly fitted on **training aircraft only** (`split_aircraft.json` train partition) to prevent split leakage:
- **Horizontal residual p95 (m):**
  - 0--50 m/s: Train = 491.91 m (All-data = 489.70 m, difference = +2.22 m)
  - 50--100 m/s: Train = 919.12 m (All-data = 918.45 m, difference = +0.67 m)
  - 100--200 m/s: Train = 1,883.64 m (All-data = 1,890.75 m, difference = -7.11 m)
  - 200+ m/s: Train = 2,505.35 m (All-data = 2,513.34 m, difference = -7.99 m)
- **Geoaltitude glitch screen (q99.9):** 2,887.98 m (train-only), screening 1,460 glitch pairs across the dataset without interpolation.

### 6.2 Altitude 15+ m/s Vertical-Rate Band Treatment
In the high vertical-rate band (|vertrate| >= 15 m/s), sample sizes are limited and train-only vs all-data p95 residuals diverge sharply:
- `baroaltitude`: Train p95 = **373.38 m** vs All-data p95 = **225.45 m** (+147.9 m difference).
- `geoaltitude`: Train p95 = **510.24 m** vs All-data p95 = **381.00 m** (+129.2 m difference).

**Recommendation:** Exclude the 15+ m/s band from altitude effect strata, or report it separately as a descriptive sensitivity subset. Calibrate shared altitude shift sizes from the stable 0--5 m/s band where baro and geo p95 residuals are closest:
- Subtle: 35.0 m
- Moderate: 125.0 m
- Blatant: 250.0 m
- Gross positive control: 500.0 m
Use one shared shift size per tier across both `baro_only` and `baro_plus_geo`.

---

## 7. Oracle Detector Benchmarks and Noise Semantics

### 7.1 Corrected Oracle Detector Results
The residual oracle detector compares horizontal pair residual against train-only speed-band p95 thresholds on 10,000 clean pairs. It was evaluated under both the default 3-step ramp and abrupt onset:

| Attack Type | Tier / Parameter | Abrupt Onset Recall | Default 3-Step Ramp Recall | Effect Quantity / Description |
|---|---|---|---|---|
| **Constant Manipulation** | Subtle (500 m) | 0.0874 | 0.0513 | 166.7 m onset step (ramp) vs 500 m (abrupt) |
| | Moderate (2,500 m) | 0.6590 | 0.1205 | 833.3 m onset step (ramp) vs 2,500 m (abrupt) |
| | Blatant (5,500 m) | 0.9991 | 0.2690 | 1,833.3 m onset step (ramp) vs 5,500 m (abrupt) |
| | Gross Control (11,000 m) | **0.9999** | **0.9754** | 3,666.7 m onset step (ramp) vs 11,000 m (abrupt) |
| **Freeze** | 90--300 s (Interior) | 0.2117 | 0.2117 | Residual = `v * dt` (interior displacement is 0) |
| | Onset step | 0.2117 | 0.0308 | Moves 33.3% of natural displacement on ramp |
| **Partial Replay** | 300 s delay | 0.9882 | 0.9855 | Kinematic discrepancy at 300 s lookback |

**Release Gate Compliance:** The gross abrupt boundary recall is **0.9999**, satisfying the >= 0.99 release gate. Gross default ramp recall is 0.9754.

### 7.2 False-Positive Rate on Maneuver-Matched Controls
- Unattacked pairs on manipulation/freeze clean controls: **4.58% FPR** (consistent with the expected ~5% false-alarm rate of a p95 threshold).
- Unattacked pairs on partial-replay matched maneuver controls: **3.87% FPR**.

### 7.3 Semantics of Eq. 12 Noise
In Li et al. (2020) Eq. 12:
$$\tilde{x}'_i = \tilde{x}_i + \kappa \cdot s, \quad s \sim \mathcal{N}(0, \sigma_{\text{step}}^2)$$
Here $\kappa$ scales the noise contribution, and $\sigma_{\text{step}} = 25.0\text{ m}$ is the base per-step noise standard deviation. The effective noise standard deviation added to each step is $\kappa \times 25.0\text{ m}$:
- Subtle ($\kappa = 0.20$): $\sigma_{\text{eff}} = 5.0\text{ m}$
- Moderate ($\kappa = 0.10$): $\sigma_{\text{eff}} = 2.5\text{ m}$
- Blatant ($\kappa = 0.05$): $\sigma_{\text{eff}} = 1.25\text{ m}$
- Gross ($\kappa = 0.00$): $\sigma_{\text{eff}} = 0.0\text{ m}$ (no noise added)

---

## 8. Summary of Approval Gate Items

Before Phase 1 attack-generation code begins, the human reviewer must approve:
1. Decoupled ground truth window rule (>= 5 attacked rows + ramp amplitude; no residual qualification requirement).
2. Reporting strata (boundary, interior-with-residual, interior-without-residual).
3. Primary dataset generated ungated on shared eligibility; residual-gated sub-analysis reported separately.
4. Long episode settings (600 s and 900 s) for interior evaluation.
5. Descriptive-only label for test speed bands with < 100 aircraft (e.g., 0--50 m/s in replay).
6. Train-only thresholds and exclusion/separate treatment of 15+ m/s vertical-rate band.
7. Corrected oracle detector benchmarks and Eq. 12 noise semantics.
