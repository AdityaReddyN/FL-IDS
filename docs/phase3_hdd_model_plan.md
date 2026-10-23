# HDD Data and Model Evaluation Plan

## Purpose and status

This plan continues the human-authorized Phase 3 work using the available
`data/hdd_data` archives. It is a pipeline-validation plan; attack labels are
synthetic, the source is decoded OpenSky state vectors, and no operational IDS
claim follows from a high score. The attached `context.docx` is review
material, not an authoritative description of files or results in this
checkout. Its January/February 2019 dataset and metrics have not been verified
here.

## Verified source inventory so far

- `data/hdd_data` contains 90 `.csv.tar` archives across four weekly dates:
  2019-11-18, 2019-11-25, 2019-12-02, and 2019-12-09. The 2019-12-02 folder
  contains 18 hourly archives; the other three contain 24 each. This is 90
  hours, not four complete contiguous days.
- Combined archive size is about 11.96 GiB. A sampled archive contains an
  inner `.csv.gz`, `README.txt`, and `LICENSE.txt`.
- One sampled CSV header matches OpenSky decoded-state-vector fields:
  `time`, `icao24`, `lat`, `lon`, `velocity`, `heading`, `vertrate`, `callsign`,
  `onground`, `alert`, `spi`, `squawk`, `baroaltitude`, `geoaltitude`,
  `lastposupdate`, and `lastcontact`.
- The embedded README describes approximately one state vector per second per
  active aircraft. The actual cadence, schema consistency, row counts,
  duplicates, time coverage, missingness, and geographic coverage have not yet
  been measured across all archives.
- The date/source description in `context.docx` (January training dates and a
  February holdout) is a separate, unverified dataset and must not be attributed
  to `data/hdd_data`.

## Data preparation

1. Read archives in place; never extract into or modify `data/raw/` or overwrite
   `data/processed/opensky_clean_v1.parquet`. Write derived artifacts only to a
   new ignored/versioned directory such as
   `data/reproductions/hdd_2019_nov_dec_v1/`.
2. Stream each tar member and its nested gzip CSV. Validate the expected columns
   and types for every hour. Record archive paths, byte sizes, SHA-256 hashes,
   parser/library versions, row counts, parse failures, and rejected rows.
3. Normalize `icao24` and numeric fields; retain the seven core state-vector
   features and the necessary metadata. Derive missing flags, heading sine/cosine,
   and contact-lag diagnostics consistently with the existing cleaner. Keep
   contact-lag fields out of model inputs pending leakage review.
4. Sort deterministically by `(icao24, time)`. Detect duplicate natural keys;
   drop exact duplicates deterministically but separately report conflicting
   duplicates rather than silently choosing a value. Create segments at gaps
   greater than 30 seconds, and report the observed inter-arrival distribution
   before selecting a sampling/time-window convention.
5. Run a read-only audit for per-date/hour coverage, rows, aircraft, segments,
   missingness, coordinate ranges, timestamp cadence, duplicate keys, and
   aircraft overlap across dates. Do not begin attack generation until this
   audit and schema validation pass.

## Split and attack construction

- Primary protocol: deterministically assign each aircraft to exactly one of
  train/validation/test (nominal 70/15/15), using all four dates only to define
  the unique aircraft universe. Save the split map and verify disjointness
  before creating windows. Do not use attack labels or test metrics to make the
  split.
- Secondary protocol: report a separate date-held-out analysis only if useful.
  It answers temporal-shift questions, not unseen-aircraft generalization; an
  aircraft seen on an earlier date may recur on the held-out date. Keep the two
  protocols and their claims separate.
- Preserve the approved episode-based v3 attack semantics and provenance where
  they apply. Use the clean, pre-attack rows for eligibility, source features,
  and geography. Never assign a geographic client from a spoofed/modified
  position. Keep one overlay per segment and retain rejection reasons.
- **Sampling-cadence gate:** do not pass this source directly to the current
  assembler. Its span/window conventions were developed around roughly
  10-second rows, while the archive README describes roughly 1-second rows.
  First measure actual deltas. Then either (a) implement and test time-based
  episode placement/window semantics at observed cadence, or (b) apply a
  deterministic, documented 10-second sampling rule. Select one before
  generating attacks; do not tune it to detector scores. Any change to approved
  attack durations, ramps, eligibility, or labels requires a documented
  decision and new tests.
- Store all original/modified feature values, source-row identity, episode and
  parameter metadata, rejected candidates, and split provenance. Ground-truth
  labels and provenance must never be model features.

## Sequence inputs and shortcut controls

- Preserve row-level labels and derive windows only within a single aircraft
  segment and split. Choose window length/stride in seconds after the cadence
  audit; record both the row count and elapsed-time meaning. Never allow
  overlapping source rows or windows to cross splits.
- Fit imputation/scaling on unique training rows only. Use explicit missingness
  masks. Derive temporal deltas/kinematic residuals only from current and prior
  rows within the same segment; preserve undefined values at starts/gaps.
- Exclude identifiers, labels, episode/provenance fields, future/global counts,
  post-attack region/client metadata, and contact-lag fields from model inputs.
  Any additional feature requires a leakage rationale and a test.
- Keep realistic-prevalence validation/test arrays. For diagnostics, also
  provide a separate training/audit view matched on eligibility, missingness,
  and window position where feasible; never replace the natural evaluation
  distribution with the matched view.
- Audit missingness-only, position-only, feature-summary, and simple kinematic
  baselines by family and stratum. Treat the attached document's reported
  near-label features (for example, velocity consistency, singleton ghost
  tracks, asymmetric filtering, and sentinel values) as specific hypotheses to
  test, not as accepted design choices.

## Models and training protocol

### Centralized Track B

- Binary normal-vs-attack and multiclass family classification use the same
  aircraft splits, windows, and model-input contract.
- Classical baselines: logistic regression and random forest over window
  summaries (per-feature mean/std/min/max, mean absolute first difference,
  missing-flag fractions, plus approved causal kinematic deltas). Preprocessing
  is fit on train only.
- Sequence models: LSTM, GRU, temporal 1D-CNN (convolutions along time, not an
  arbitrary feature ordering), and a small Transformer encoder. Use one
  training/evaluation harness, CPU-first settings, deterministic seeds, and
  validation-only early stopping.
- Binary model selection: validation PR-AUC is primary because attack
  prevalence is low; also report ROC-AUC. Multiclass selection uses validation
  macro-F1. Set operating thresholds on validation normal windows for target
  FPRs (1% and 5%); report the resulting test recall and FPR without retuning.
- Run at least five seeds per selected model. Report mean and 95% intervals;
  use aircraft-cluster resampling when enough aircraft support it, otherwise
  label the uncertainty as seed-level only. Report per-family and
  boundary/interior/none stratum metrics when sample sizes permit.
- Track A (normal-only autoencoder) is a later, separate novelty-detection
  experiment. Attack labels may be used for evaluation only, never training or
  threshold fitting beyond validation-normal FPR calibration.

### Federated Track

- OpenSky files do not identify actual receivers. A position-grid partition is
  therefore a **simulated geographic client assignment**, not evidence of real
  receiver identities or receiver coverage. State this in configs and reports.
- To keep aircraft isolated across clients, assign each aircraft to one client
  using its modal **pre-attack** grid cell with deterministic tie-breaking;
  report how often aircraft traverse other cells. Never move an attacked row to
  a different client because its coordinates were modified.
- Compare local-only, FedAvg, and later FedProx/FedAdam with a centralized model
  of the same architecture, features, splits, and training budget. Keep a
  centralized engineered-feature baseline as an additional reference, not as
  the sole comparator for a neural FL model.
- Avoid pooled preprocessing or global class weights that would require
  centralizing client data unless explicitly presented as a centralized
  reference. Report client sizes/heterogeneity, rounds, communication, runtime,
  and per-client validation results. Select rounds/hyperparameters on
  validation, never the test split.

## Evaluation and interpretation

Report ROC-AUC, PR-AUC, per-family precision/recall, normal FPR, recall at
validation-calibrated FPR, confusion matrices, and latency where measured.
Always state test prevalence. Prior correction is a sensitivity analysis only;
derive it from the actual training and target priors under an explicit
label-shift assumption, and do not tune it on test. No step in this plan
guarantees ROC-AUC 0.9. A lower result with leakage-resistant evaluation is
preferable to a high score explained by synthetic labels or split artifacts.

## Stage order and gates

1. HDD archive/schema/cadence audit (read-only inputs).
2. Test-first streaming cleaner and validation report; new versioned output.
3. Cadence decision and test-first adaptation of episode/window semantics.
4. Aircraft split, attack generation, provenance/schema/shortcut validation.
5. Phase 3 centralized model comparisons, registered before runs; select on
   validation and evaluate locked test once.
6. Phase 4/5 geographic client maps and FL comparisons after centralized
   pipeline review. Stop at the Phase 3 gate before proceeding unless the human
   has explicitly authorized that transition.
