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
arrays retain natural prevalence. Gate 2 is not passed: the summary-statistic
shortcut baseline remains informative; see E-002 and `PROGRESS_LOG.md`. Do not
start Phase 3 before the shortcut criterion is resolved and Gate 2 is reviewed.
