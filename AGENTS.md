# AGENTS.md — FL-IDS for ADS-B

Instructions for any coding agent (Codex, Claude Code, etc.) working in this repo.
Read this file fully at the start of every session.

## 1. Mission

Build and rigorously evaluate a **federated-learning-based intrusion detection
system (IDS) for ADS-B surveillance data**, with the end goal of a research
paper titled roughly *"Federated Learning based IDS for ADS-B enabled systems"*.

Pipeline: OpenSky ADS-B state vectors -> synthetic attack injection (grounded in
Li et al. 2020, IET Information Security 14(5), doi:10.1049/iet-ifs.2018.5635)
-> sequence windows -> centralized / local / federated detectors -> evaluation.

The paper's intended contribution: ADS-B-specific FL-IDS where **receiver/region
coverage creates natural non-IID data**, compared across aggregation methods,
model families and robustness settings, with honest, leakage-free evaluation.

## 2. Context protocol (MOST IMPORTANT — you have no memory between sessions)

The `docs/` folder is your memory. If it is not written there, it did not happen.

**At session start, read in this order:**
1. `AGENTS.md` (this file)
2. `docs/PROJECT_CONTEXT.md` — current snapshot of the project (rewritten in place)
3. `docs/ROADMAP.md` — phases, tasks, checkboxes, current phase
4. Last ~5 entries of `docs/PROGRESS_LOG.md`
5. `docs/DECISIONS.md` and `docs/EXPERIMENT_REGISTRY.md` (skim; search when relevant)
6. `nextSteps.md` (repo root) — the staged recovery plan; do only the first
   unchecked stage. (`docs/CHAT_HANDOFF.md` is superseded; see `docs/MASTER_CONTEXT.md`
   if present.)

**During work:**
- Record every non-trivial design choice in `docs/DECISIONS.md` (append-only, numbered `D-###`).
- Register every experiment run in `docs/EXPERIMENT_REGISTRY.md` (append-only, `E-###`)
  BEFORE running it (status `planned`), then fill in results after. Copy numbers
  from the actual result files; never from memory or estimation.

**At session end (always, even if work is unfinished):**
1. Append an entry to `docs/PROGRESS_LOG.md` using the template in that file.
2. Tick/untick checkboxes in `docs/ROADMAP.md` and update "Current phase".
3. Rewrite the relevant sections of `docs/PROJECT_CONTEXT.md` so it reflects
   reality now (it is a snapshot, not a log: keep it short and current).
4. Commit docs together with the code they describe.

Keep docs concise and factual. No marketing language. Mark uncertainty explicitly
("unverified", "assumed"). Never delete history from append-only files; if
something was wrong, add a correction entry referencing the old ID.

## 3. Non-negotiable rules

**Data integrity**
- NEVER modify or overwrite these immutable artifacts: `data/raw/`,
  `data/processed/opensky_clean_v1.parquet`, `data/sequences/`,
  `data/sequences_v2/`, `results/centralized_lstm/`. Anything new goes into a
  new versioned directory (e.g. `data/attack_generation_v3/`, `data/sequences_v3/`).
- `data/` and `results/` are gitignored. Do not commit data or model weights.
  Commit code, configs, docs, and small summary tables only.

**Scientific honesty**
- Do not invent details of Li et al. (2020). Several equations are not
  accessible as text. Anything not verifiable from the paper must be labelled an
  **implementation choice** in code docstrings, config, `DECISIONS.md`, and the
  dataset manifest.
- Data is **decoded OpenSky state vectors, not raw 112-bit ADS-B messages**. Say
  so in all docs and paper text. Attacks are data-layer simulations.
- Attack labels are synthetic. Never write claims implying operational
  aviation-IDS performance.
- Report results exactly as measured. If a result looks too good (>0.99 F1),
  treat it as a suspected leak/shortcut and investigate before reporting.

**Leakage and validity**
- Split by **aircraft (`icao24`)** before any window generation. Where the
  experiment is about geography, also support splitting by **region**.
- Fit imputers/scalers on **training data only**.
- Never tune on the test split. Model selection uses validation only.
- Windows derived from the same source window (normal vs attacked copies) must
  stay in the same split.

**Reproducibility**
- Every script takes `--seed` and writes a `config.json` and, for datasets, a
  `manifest.json` (inputs, params, git commit hash, counts, rejected candidates).
- Experiments run with >= 5 seeds before any number goes into a paper table.
- Pin dependencies in `requirements.txt`. Record library versions in run configs.

**Working style**
- Work **one roadmap phase at a time**. At each phase gate (end of phase),
  stop, summarize in `PROGRESS_LOG.md`, and wait for the human to approve before
  starting the next phase.
- Prefer small, reviewable commits with clear messages (`phase1: add gradual
  deviation attack`).
- Add tests for anything that generates labels or splits data.
- Do not refactor or delete legacy scripts unless a roadmap task says so
  (move to `scripts/legacy/` rather than deleting).
- If requirements are ambiguous or a decision materially changes the science,
  ask the human instead of guessing. Log the answer in `DECISIONS.md`.

## 4. Current repo state (as of project handoff)

Existing scripts in `scripts/`:
- `build_dataset.py` -> `data/processed/opensky_clean_v1.parquet` (merge raw CSVs;
  7 core features + missing flags; heading sin/cos; segments split at >30 s gaps)
- `build_sequences_v2.py` -> `data/sequences_v2/` (window 30, stride 10, 15
  features = 8 continuous + 7 missing flags; aircraft-level 70/15/15 split;
  train-only imputer/scaler; 5 balanced classes)
- `train_centralized_lstm.py` -> `results/centralized_lstm/<run>/` (1-layer
  LSTM-64, early stopping on val macro-F1, single seed)
- Various `*_audit.py`, `validate_*.py` scripts; `build_sequence.py` and
  `validate_sequence.py` are v1 (legacy).
- `docs/attack_generation_methodology.md`: mapping of Li et al. to this repo and
  the planned v3 scope. Treat as authoritative for what is/isn't reproducible.

**There is no federated code yet.** `train_client_ids.npy` in v2 assigns
windows to 5 clients uniformly at random (IID) and is a placeholder only.

## 5. Known weaknesses to fix (from code review)

1. v2 attacks are ad hoc fixed offsets (lat +-0.15, lon +-0.20, velocity +-80 m/s,
   altitude +-2500 m, freeze), not Li et al. They are trivially detectable
   discontinuities.
2. Shortcut risk: attacks are only placed in fully observed intervals while
   normal windows may contain missing values; attack intervals are always
   confined to roughly [len/3, len-2) of the window.
3. Classes are balanced 1:1:1:1:1, unrealistic vs. paper's attack proportion
   (<= ~10%, 0.05% in their simulation).
4. Client assignment is IID-random, ignoring aircraft and geography.
5. Single seed, single model, no confidence intervals.
6. Only ~2 hours of data (verify actual coverage and record in PROJECT_CONTEXT).
7. Window-level attack injection prevents attacks spanning windows or realistic
   episode structure; v3 must inject at **row level** first.

## 6. Target layout (create gradually; don't big-bang refactor)

```
AGENTS.md
README.md
requirements.txt
configs/            # YAML/JSON experiment configs
docs/               # context docs (see section 2) + methodology
scripts/            # thin CLI entry points (existing + new)
scripts/legacy/     # v1 scripts moved here in Phase 0
src/flids/
    attacks/        # row-level attack generators + validators
    data/           # windowing, splits, preprocessing, client partitioning
    models/         # LSTM, GRU, CNN1D, Transformer, autoencoder
    fl/             # client, server, aggregators, simulation loop
    eval/           # metrics, plots, tables
tests/
```

## 7. Roadmap (full detail with checkboxes lives in `docs/ROADMAP.md`)

### Phase 0 — Housekeeping and baseline reproduction
- Create `requirements.txt`, `README.md` (how to run each stage), `tests/` skeleton.
- Move v1 scripts to `scripts/legacy/`.
- Re-run v2 pipeline end to end on the real data and confirm the existing
  centralized LSTM result is reproducible. Record numbers in the registry.
- Fill in `docs/PROJECT_CONTEXT.md` with measured facts: rows, aircraft,
  segments, time range, geographic bounding box, missingness rates.
- **Gate:** human approves baseline numbers and context doc.

### Phase 1 — Row-level attack generation v3 (paper-grounded)
Output to `data/attack_generation_v3/`. Never mutate v2 arrays.
- Implement attacks on the **row-level cleaned table**, preserving
  `icao24`/`segment_id`/`time`:
  - Data manipulation on lat, lon, baro/geo altitude: constant deviation,
    random (Gaussian) deviation, increased/gradual deviation. Then, if time
    allows, non-linear (square), zoom/static magnification, changeable
    time-varying deviation.
  - Data replay: replace current observations with same-aircraft observations
    from ~300 s earlier (paper value); only where lookback exists in the same
    aircraft history. Call it "stale-track/data-layer replay".
  - Ghost injection and DoS: **deferred** unless the human supplies the paper
    PDF or approves implementation choices. Stub with clear NotImplemented +
    doc entry.
- Target selection: random, area-based, neighbour-based (documented in paper).
- Attack proportion: parameterised, default <= 0.1 of aircraft/rows; support a
  sweep (e.g., 0.5%, 1%, 5%, 10%).
- Amplitude: derive from historical per-feature statistics (e.g., multiples of
  the per-step delta std or percentiles) rather than fixed constants, and offer
  **stealth tiers** (subtle / moderate / blatant). Document as implementation
  choice.
- Episode structure: attacks are intervals of variable length in time (seconds),
  can span what will later become multiple windows.
- Store for every modified row: original values, modified values, attack
  type, episode id, parameters, source row id. Store rejected candidates and why.
- Physical plausibility report per attack (from methodology doc): geodesic
  step distance, implied groundspeed vs reported velocity, accel proxies,
  turn rate, vertical rate vs altitude change, continuity before/during/after.
- Write `manifest.json` with seeds, params, counts, limits (what cannot be
  checked from state vectors: RF replay fidelity, signal strength, bit-level).
- Tests: label correctness, no cross-aircraft contamination, determinism by
  seed, replay delay exactly as configured, no changes outside intervals.
- **Gate:** human reviews manifest + plausibility report + plots.

### Phase 2 — Sequence dataset v3 + shortcut audit
Output to `data/sequences_v3/`.
- Windows from the attacked row table; window label rules documented (e.g.,
  attack if >= k attacked rows; also store per-step labels for detection-latency
  analysis).
- Aircraft-level split before windowing; train-only preprocessing; keep source
  windows together.
- Provide both **balanced** (for training) and **realistic-prevalence**
  (for evaluation) test sets.
- Provide binary (normal vs attack) and multiclass labels.
- Remove v2 shortcuts: attack placement uniform over the window; normal windows
  must have comparable missingness to attacked ones (or condition both the
  same way).
- **Shortcut audit script:** train trivial baselines on (a) missingness
  flags only, (b) position-in-window only, (c) per-feature summary stats.
  Each should be near chance; if not, fix the generator and log it.
- **Gate:** shortcut audit passes; human approves.

### Phase 3 — Centralized baselines (upper bound)
- Models: logistic regression / random forest on engineered features, LSTM,
  GRU, 1D-CNN, small Transformer; optionally an unsupervised autoencoder
  (trained on normal only) for unseen-attack generalization.
- Metrics: accuracy, macro-F1, per-class precision/recall/F1, PR-AUC, ROC-AUC,
  recall at fixed FPR (e.g., 1%), false-positive rate on normal, detection
  latency, parameter count, inference time.
- >= 5 seeds, mean and 95% CI. Registry entry per model.
- **Gate:** baseline table approved.

### Phase 4 — Federated client partitioning
- Implement partition strategies, each saved as a client-map file with a
  heterogeneity report (label distribution, feature distribution, size per client):
  1. IID random (control)
  2. **Geographic**: grid cells / clusters of lat-lon simulating receivers
     (primary realistic non-IID)
  3. Aircraft-group partition (all windows of an aircraft stay on one client)
  4. Dirichlet label skew (alpha in {0.1, 0.5, 1.0})
  5. Quantity skew
- Partition by aircraft so no aircraft appears on two clients.
- **Gate:** human approves partition design and reports.

### Phase 5 — Federated learning framework and experiments
- Simulation (Flower simulation or a clean custom PyTorch loop; log the choice).
- Algorithms: local-only, FedAvg, FedProx, FedAdam (and SCAFFOLD if feasible),
  plus personalization (post-hoc fine-tuning, FedPer-style head).
- Config: rounds, local epochs, client fraction, lr, batch size, mu for FedProx.
  Hyperparameter search on validation only, same budget for all methods.
- Log per round: global val metrics, per-client metrics, bytes communicated,
  wall-clock. Save round curves.
- Compare against centralized (upper bound) and local-only (lower bound) under
  every partition from Phase 4.
- **Gate:** human reviews first full results table.

### Phase 6 — Robustness and privacy (differentiators)
- Malicious clients: label flipping and model/update poisoning at 10/20/30%.
- Robust aggregation: coordinate median, trimmed mean, Krum.
- Optional: DP-SGD / clipping+noise with epsilon reporting; communication
  efficiency (update compression).
- Evaluate on held-out aircraft AND held-out regions; evaluate on attack types
  unseen during training (generalization).

### Phase 7 — Evaluation, ablations, figures
- Scripts that regenerate **every** table/figure in the paper from result files
  (`scripts/make_tables.py`, `scripts/make_figures.py`); no manual numbers.
- Ablations: window length, stealth tier, attack proportion, number of clients,
  local epochs.
- Statistical tests or CIs for headline comparisons.

### Phase 8 — Paper support
- `docs/PAPER_OUTLINE.md`: structure, claims-evidence matrix (each claim -> the
  experiment IDs that support it), limitations section (synthetic labels,
  decoded state vectors, limited time/geography), related-work table
  (FL-IDS for UAV/FANET/IoV, ADS-B attack detection, ADS-B attack synthesis).
- Keep a `docs/LIMITATIONS.md` updated throughout, not just at the end.

## 8. Experiment conventions

- Run directory: `results/<experiment_id>/<run_name>/` containing `config.json`
  (all hyperparameters, seed, git commit, library versions, data version),
  `metrics.json`, `history.csv`, `confusion_matrix.csv`, and predictions.
- Experiment IDs match `docs/EXPERIMENT_REGISTRY.md` (`E-###`).
- Primary selection metric on validation: macro-F1 (multiclass) or PR-AUC (binary).
- Always report FPR on normal data alongside detection metrics.

## 9. When you finish a task

Say what changed, where, what you ran, what the output was, and what you did
NOT verify. Then update the docs per section 2. Do not claim something works
unless you ran it.
