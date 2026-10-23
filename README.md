# FL-IDS for ADS-B

Research code for a federated-learning IDS study using decoded OpenSky ADS-B
state vectors and synthetic, data-layer attack labels. It is not an operational
aviation IDS and does not use raw 112-bit ADS-B messages.

## Phase 0 baseline reproduction

Use Python 3.12 and install `requirements.txt`. Immutable baseline artifacts
are never overwritten; this command sequence writes to new ignored paths:

```powershell
python scripts/build_dataset.py --raw-dir data/raw --out-dir data/reproductions/phase0/processed --seed 42
python scripts/validate_dataset.py --input data/reproductions/phase0/processed/opensky_clean_v1_reproduced.parquet
python scripts/build_sequences_v2.py --input data/reproductions/phase0/processed/opensky_clean_v1_reproduced.parquet --out-dir data/reproductions/phase0/sequences_v2_seed42 --seed 42
python scripts/validate_sequences_v2.py --root data/reproductions/phase0/sequences_v2_seed42
python scripts/train_centralized_lstm.py --data-dir data/reproductions/phase0/sequences_v2_seed42 --results-dir results/E-001 --run-name reproduction_seed42 --seed 42
```

Run checks with `python -m pytest`. Legacy v1 sequence scripts live in
`scripts/legacy/` for provenance only. The active context records live in
`docs/`.

## Phase 2 sequence pipeline (pipeline validation only)

The accepted seed-42 Stage C attack tables are under
`data/attack_generation_v3/stage1_seed_42_retry4/`. Build a new sequence output
without overwriting an existing directory:

```powershell
python scripts/build_sequences_v3.py --input-dir data/attack_generation_v3/stage1_seed_42_retry4 --out-dir data/sequences_v3/seed_42_rerun_1 --seed 42
python scripts/audit_shortcuts_v3.py --dataset-dir data/sequences_v3/seed_42_rerun_1 --out results/E-002/shortcut_audit_rerun_1.json --seed 42
```

This is pipeline validation on decoded state vectors with synthetic labels, not
a scientific or operational-security result. The realistic validation/test
arrays retain natural prevalence. The summary-statistic shortcut baseline
remains informative (E-002); the human authorized Phase 3 to proceed while
retaining that caveat (D-034). This does not mean the audit passed.

## Phase 3 and HDD plan

The initial five-seed binary LSTM run on current v3 data is registered as E-003
and is pipeline validation only. Its mean test ROC-AUC is 0.5742; this does not
meet the desired 0.9 target, which is not guaranteed. Do not tune on test data.

`data/hdd_data` has 90 hourly tar archives (~11.96 GiB) across four weekly
dates. One sampled inner CSV has decoded OpenSky state-vector columns and its
README describes roughly 1 Hz, while the current attack/window pipeline expects
roughly 10-second rows. Audit actual cadence and schemas before adapting or
generating attacks. Follow `docs/phase3_hdd_model_plan.md`; it specifies
streaming preparation, aircraft-first splits, episode-level synthetic attacks,
leakage controls, centralized models, and later simulated-geography FL.
