# li2020_extracted_details.md

**Source:** Li, Wang, Shang, Tian, Cao (2020), "Threat model and construction
strategy on ADS-B attack data", IET Information Security 14(5), 542-552,
doi:10.1049/iet-ifs.2018.5635. Local PDF: `docs/references/` (gitignored).
**Reference code:** https://github.com/litengyao/adsb-attack-data-generator
(Apache-2.0; self-described "developing"; contains bugs, see section 6).

This file supersedes the "equations unavailable" statements in
`attack_generation_methodology.md`. Notes below are paraphrased summaries plus
the paper's equations. Tag meaning: **[PAPER]** stated in the paper,
**[CODE]** only visible in the authors' code, **[CHOICE]** our implementation
choice (not in either source), **[AMBIGUOUS]** unclear or inconsistent.

## 1. Data model and fields
- [PAPER] Sequential data for flight j in window T_w: X_j^w = {x_i | i = t_0..t_n}.
  Each point x_i has attributes k in Q with x_i^k = eta_k (s_i^k + nu_k), where
  eta_k in {0,1} is a missing-data indicator, nu_k in [0, nu_max] is noise.
  Constraints: |Q| >= m, neighbouring-point variance D(|x_{i+1}-x_i|) <= eps_x,
  local flight density d <= eps_d. (Eq. 1)
- [PAPER] Simulation data: OpenSky, recoded at 10 s separation. Four-dimensional
  track = lat, lon, barometric altitude, time. Flight-status data = heading,
  velocity, vertical rate, geo altitude.
- [PAPER] Step I: decode to structured data; drop sequences whose missing
  percentage is high, otherwise keep as is.
- [PAPER] Labels are added to normal and constructed attack data for evaluation
  only; labels must not be used to train detectors. The paper argues for
  treating ADS-B data as unlabelled and using unsupervised/novelty detection.

## 2. Four attack families and equations
All attacks occur within an attack time window T_w (attacks need not span the
whole flight). Section 4 of the paper.

### 2.1 Data manipulation (targets: flights)
- Additive (Eq. 2): x~_i = x_i + xi * a_i, i in T_w. xi scales strength.
  - Random deviation: a_i^k ~ N(mu, sigma^2) (Gaussian) [PAPER].
  - Constant deviation: a_i^k = C, with C of the same order of magnitude as
    the attribute [PAPER].
  - Increased deviation: a_i^k = C * f(i); example f(i) = ln(1 + i - t0) so
    injection speed slows over time [PAPER].
- Multiplicative (Eq. 3): x~_i = g(x_i) x_i.
  - Static magnification: g = lambda (constant) [PAPER] ("zoom").
  - Non-linear: g only approximable; example given: holding a value fixed for a
    long time, g(x_i) = x_{t0}/x_i [PAPER]. **Note: this "fixed-value sequence"
    is a manipulation example, not the paper's replay attack.**
- Table 1 of the paper lists six implemented variants: constant, random,
  increased (specific ratio), nonlinear (squared deviation), zoom (constant
  multiplicative factor), changeable (deviation changing with time).
- [PAPER] Modified attributes in simulation: latitude, longitude, altitude.
  Partial modification is stealthier than whole-message corruption; small
  deviations that force flights into fault states gradually are hardest to detect.
- [PAPER] Attack share in the simulation dataset: 0.05%.

### 2.2 Ghost flight injection (targets: airspaces)
- Eq. 4 copied ghost: ghost track = neighbouring flight's sequence (new ICAO).
- Eq. 5 created ghost: generated point by point from motion laws; uniform linear
  motion x_{i+1}^loc = x_i^loc + x_i^v * dt; uniformly accelerated variant
  (**[AMBIGUOUS]**: the printed accelerated formula omits the position term).
- Eq. 6 random ghost: x~_i = a_h, random values (Gaussian example).
- Eq. 7 historical ghost: X~_j = X'_j, same flight's data from several days earlier.
- Table 2 (simulated): copied, created, random. (Historical not simulated.)
- Mixed into normal data via the mixture strategies of section 4 below.

### 2.3 Data replay (targets: flights)
- Eq. 8: x~_i = x_{i - dt_a}. dt_a is the key parameter. **dt_a = 300 s in the
  paper's simulation** [PAPER].

### 2.4 DoS / message blocking (targets: airspaces)
- Eq. 9: during the window, data is replaced by receiver noise epsilon (i.e. effectively
  absent). a_w is the window length; a_w = T_w means deletion over the whole window.
- Table 3 variants: period DoS (single window; **360 s** in simulation), whole DoS
  (delete all data), cycle DoS (periodic; **normal:attack time ratio 5:3**).

Composite attacks (several patterns at once) are mentioned; build from basic patterns.

## 3. Construction framework (six steps)
I prepare normal data -> II target selection -> III key parameters -> IV simulate
attack effect -> V mix attack with normal data -> VI persist labelled dataset.

### 3.1 Target selection (section 5.1)
- Manipulation and replay select **flights**; ghost and DoS select **airspaces**.
- Random selection: split airspace into similar-area sub-airspaces (orthogonal
  partition), choose flights uniformly within each.
- Area selection: all flights inside given geographic bounds.
- Neighbour selection: one centre flight plus flights within a radius (radius ~0
  = only the centre; default = flights within ADS-B communication range).

### 3.2 Key parameters (section 5.2)
- Attack proportion (Eq. 10): eta = tau * rho_0 * log(1 + theta) / rho, with
  tau in [0, 0.1] (basic proportion), theta in [0, 1] (attack strength), rho =
  flight density, rho_0 = historical-data normaliser of rho into [0,1]. Higher
  density -> lower proportion; higher strength -> higher proportion with
  saturation. (The printed range "[0. 0.1]" is a typo for [0, 0.1].)
- Amplitude zeta (Eq. 11): bounded using historical statistics: |zeta| <= (x_m / x_i)
  * sqrt((x_i - xbar_i)^2 + x_i^2), with xbar the average and x_m the maximum of
  the attribute. **[AMBIGUOUS]**: the exact reading of this bound (index
  conventions) is not clear from the text; document the interpretation used.
- Noise on attack data (Eq. 12): x~'_i = x~_i + kappa * s, s ~ N(mu, sigma), with
  mu = 0 and sigma "small" (value not given), kappa in [0,1] controls noise share.
- Efficiency/stealth metric (Eq. 13): Gamma = eta * (1/|T_a|) * sum_{t in T_a}(zeta/x_m) - kappa.
  Higher Gamma = more effective; lower Gamma = stealthier. Usable to define stealth tiers.

### 3.3 Mixture strategies (section 5.3, for ghost injection)
- Uniform: same number of fake nodes injected per sub-airspace at random locations.
- Route: band around a specific flight's route.
- Hot point: fake nodes concentrated around a chosen centre flight.

## 4. What the paper does NOT specify (all remain [CHOICE])
Numeric values for C, sigma, lambda, f's scale, xi, kappa, sigma of noise;
ghost counts; ghost injection locations/distributions; spatial neighbourhood
radius; validation metrics beyond visual plots and Gamma. No detection
experiments exist in the paper; it validates construction qualitatively with
plots on real OpenSky data. The authors state the strategy does not cover
signal-level properties (signal strength, Doppler, timing).

## 5. What the authors' reference code reveals [CODE]
- Whole-flight attacks on a **random 0.05% of flights** (`percent = 0.0005`).
  This is what the paper's "0.05%" refers to. With ~14k aircraft that is only ~7
  aircraft: **too few for ML**; use eq. 10 with tau up to 0.1 and sweeps instead.
- Replay: shifts by `time_span/10` records (300 s -> 30 records), only on
  lat, lon, baroaltitude; first rows filled from the earliest shifted record.
- Constant deviation test: [2.5 deg, 2.5 deg, 2000 m] on (lat, lon, baroaltitude),
  i.e. blatant. Zoom factors tested: [2.0, 3.0, 1.5]. Increased deviation: initial
  [0.0005, 0.0005, 0.01], ratios [0.0002, 0.0002, 0.000005]. Changeable: base
  [0.25, 0.25, 200] times ln(1 + t).
- Random deviation in code: uniform in [0, 0.035 * (max - min of that aircraft's
  attribute)], one-sided, **not Gaussian** as the paper text says.
- DoS in code: values set to NaN (rows kept) for 7 features; period test window
  = 360 s; cycle test = 50 normal records then 30 attacked records (5:3).
- Ghost copy: translates a neighbour's track to a chosen location with a new ICAO.
- Data: OpenSky state vectors (same source as this project).

## 6. Known bugs/oddities in the reference code (do NOT copy blindly)
- `inject_increase_deviation` / `inject_changeable_deviation` appear to add to
  the **entire aircraft column on every loop iteration** instead of a per-row
  growing deviation (verify before relying on behaviour).
- `random_ghost` computes `np.add(...)` and `pd.concat(...)` without assigning
  the results (no effect). `create_ghost` steps lat by ~15 deg per sample
  (50*0.3) which is physically implausible.
- 'area' selection compares longitude to `start_lat`; 'random' selection uses
  `random_integers(0, n)` (can index out of range, samples with replacement).
- Several functions are marked "status: developing".
**Therefore: reimplement from the paper's equations, using the code only as a
cross-check for parameter scales. Cite the repo and keep the Apache-2.0 notice
if any code is adapted.**

## 7. Related work to cite
Habler & Shabtai (2018), "Using LSTM encoder-decoder algorithm for detecting
anomalous ADS-B messages", Computers & Security 78, 155-173. Their five attack
sets: random noise, route (replace with another flight for some windows),
gradual altitude drift, velocity drift, message blocking (keep 1 of every 5
messages). Our v2 classes resemble these; Habler is the natural detector
baseline (LSTM encoder-decoder, unsupervised).

## 8. Implications and PROPOSED decisions (agent: copy into DECISIONS.md as D-004...)
- **D-004 (proposed): Attack proportion.** Use eq. 10 with tau swept over
  {0.005, 0.01, 0.05, 0.1}; do not use the paper's 0.05% flight share (too few
  aircraft). Document as deviation. Type: implementation choice.
- **D-005 (proposed): Amplitude and stealth.** Derive amplitudes from per-attribute
  historical statistics following eq. 11 (state the interpretation used) and
  define three stealth tiers via Gamma/zeta ranges. Add Gaussian noise (eq. 12).
  Type: implementation choice.
- **D-006 (proposed): Two detection tracks.** (A) Novelty/semi-supervised track
  matching the paper's stance that labels are for evaluation only: train on
  (mostly) normal data, e.g. LSTM autoencoder or encoder-decoder à la Habler,
  federated across clients. (B) Supervised multiclass track as an upper bound.
  Headline FL results should include track A. Requires human approval.
- **D-007 (proposed): Rename v2 "replay_freeze_sim".** It corresponds to the
  paper's fixed-value-sequence manipulation example (eq. 3), not replay (eq. 8).
  Phase 1 adds true delayed replay (300 s, lat/lon/baroaltitude minimum, optionally all fields).
- **D-008 (proposed): Enable previously deferred attacks.** Ghost injection
  (copied, created via uniform linear/accelerated motion with plausible
  parameters, random) and DoS (period 360 s, whole, cycle 5:3) are now
  specified well enough to implement. Ghost aircraft must stay in the same
  split as their source aircraft; give them reserved ICAO IDs (e.g. prefix `GH`).
  DoS as NaN windows risks a missingness shortcut: handle through the Phase 2
  shortcut audit and by matching missingness statistics in normal data.
- **D-009 (proposed): Episode-level injection** (attack time window T_w within a
  flight, eq. 2 allows i in T_w) alongside whole-flight attacks as in the paper.
