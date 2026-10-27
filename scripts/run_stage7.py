"""Stage 7 generation driver (D-045): preflight -> capacity -> benchmark ->
[human approval] -> pilot -> validate -> A -> validate -> B -> validate ->
C -> validate.

Resumable via marker files under results/stage7/markers (gitignored); stops on
the first failure and prints the resume command; `--dry-run` prints the phase
plan and writes nothing. The driver NEVER edits tracked files: it writes only
under data/attack_generation_v3/, results/, and logs/ (all gitignored). The
agent does not run this; the human does.

Gate: generation phases (pilot/A/B/C) run only when --approved-cells POINTS at
the human-approved prioritized cell list (D-045 step 2); without it the driver
stops after the benchmark.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

MARKERS = ROOT / "results" / "stage7" / "markers"
LOGS = ROOT / "logs" / "stage7"
PY = sys.executable


def _marker(name: str) -> Path:
    return MARKERS / f"{name}.done"


def _run(cmd: list[str], log: Path) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    with log.open("w", encoding="utf-8") as handle:
        proc = subprocess.run(cmd, stdout=handle, stderr=subprocess.STDOUT, text=True)
    return proc.returncode


def _git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def preflight(args) -> list[str]:
    problems = []
    try:
        if _git(["status", "--porcelain"]).strip():
            problems.append("working tree is dirty (commit first)")
        commit = _git(["rev-parse", "HEAD"])
    except Exception as error:  # noqa: BLE001
        problems.append(f"git unavailable: {error}"); commit = "unknown"
    subset = args.subset if args.subset.is_absolute() else ROOT / args.subset
    if not subset.exists():
        problems.append(f"subset parquet missing: {subset}")
    manifest = subset.with_suffix(".manifest.json")
    fingerprint = json.loads(manifest.read_text(encoding="utf-8")).get("content_fingerprint") if manifest.exists() else None
    import shutil
    free_gb = shutil.disk_usage(ROOT).free / 1e9
    if free_gb < args.min_free_gb:
        problems.append(f"only {free_gb:.1f} GB free (< {args.min_free_gb})")
    if not args.skip_tests:
        rc = _run([PY, "-m", "pytest", "-q"], LOGS / "preflight_pytest.log")
        if rc != 0:
            problems.append("pytest failed (see logs/stage7/preflight_pytest.log)")
    print(f"  commit={commit} subset_fingerprint={fingerprint} free={free_gb:.1f}GB")
    return problems


def capacity(args) -> list[str]:
    out = ROOT / "results" / "stage7" / "capacity.json"
    rc = _run([PY, str(ROOT / "scripts" / "capacity_study.py"),
               "--input", str(args.subset), "--splits", str(args.split), "--out", str(out)],
              LOGS / "capacity.log")
    return [] if rc == 0 else ["capacity_study failed"]


def benchmark(args) -> list[str]:
    import pandas as pd
    sys.path.insert(0, str(ROOT / "scripts"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("benchmark_generation", ROOT / "scripts" / "benchmark_generation.py")
    bench = importlib.util.module_from_spec(spec); spec.loader.exec_module(bench)
    from flids.attacks.config import load_approved_config, load_run_plan
    from flids.attacks.run_config import overlays_from_plan, quota_targets_from_plan
    config = load_approved_config(args.config)
    plan = load_run_plan(args.plan_b)
    overlays = overlays_from_plan(config, plan)
    frame = pd.read_parquet(args.subset)
    sample_ids = frame["icao24"].drop_duplicates().head(args.benchmark_aircraft)
    sample = frame[frame["icao24"].isin(sample_ids)].reset_index(drop=True)
    split = json.loads((ROOT / args.split if not args.split.is_absolute() else args.split).read_text(encoding="utf-8"))
    of = {str(ic): name for name, ids in split.items() for ic in ids}
    result = bench.benchmark(sample, overlays, args.seed, lambda ic: of.get(str(ic)),
                             quota_targets_from_plan(config, plan))
    est_hours = (len(frame) / result["rows_per_second"]) / 3600.0 if result["rows_per_second"] else None
    (ROOT / "results" / "stage7" / "benchmark.json").write_text(
        json.dumps({**result, "estimated_full_subset_hours": est_hours}, indent=2, sort_keys=True), encoding="utf-8")
    print(f"  rows/s={result['rows_per_second']:.0f}  estimated full-subset hours={est_hours:.2f}")
    if est_hours is not None and est_hours > args.max_hours_per_run:
        return [f"estimated {est_hours:.2f} h > --max-hours-per-run {args.max_hours_per_run}"]
    return []


def _generate_and_validate(label, plan, out_name, conflict_order, args) -> list[str]:
    out = ROOT / "data" / "attack_generation_v3" / out_name
    gen = [PY, str(ROOT / "scripts" / "generate_attack_v3.py"), "--plan", str(plan),
           "--seed", str(args.seed), "--out", str(out), "--input", str(args.subset),
           "--progress-log", str(LOGS / f"{label}_progress.jsonl")]
    if conflict_order == "plan":
        gen += ["--conflict-order", "plan"]
    if _run(gen, LOGS / f"{label}_generate.log") != 0:
        return [f"{label}: generation failed"]
    report = ROOT / "results" / "stage7" / f"validate_{label}.json"
    val = [PY, str(ROOT / "scripts" / "validate_generated_dataset.py"), str(out),
           "--source", str(args.subset), "--split", str(args.split), "--report", str(report)]
    if _run(val, LOGS / f"{label}_validate.log") != 0:
        return [f"{label}: validation FAILED (see {report})"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subset", type=Path, default=Path("data/processed/hdd_clean_v1_subset_10pct.parquet"))
    parser.add_argument("--split", type=Path, default=Path("data/processed/hdd_clean_v1/split_aircraft.json"))
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "attack_v3_stage1.yaml")
    parser.add_argument("--plan-a", type=Path, default=ROOT / "configs" / "run_plans" / "plan_A_per_cell_eval.yaml")
    parser.add_argument("--plan-b", type=Path, default=ROOT / "configs" / "run_plans" / "plan_B_mixed_realistic.yaml")
    parser.add_argument("--plan-c", type=Path, default=ROOT / "configs" / "run_plans" / "plan_C_trackB_training.yaml")
    parser.add_argument("--approved-cells", type=Path, default=None,
                        help="path to the human-approved prioritized cell list; required to run generation")
    parser.add_argument("--max-hours-per-run", type=float, default=2.0)
    parser.add_argument("--min-free-gb", type=float, default=20.0)
    parser.add_argument("--benchmark-aircraft", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    pre_gen = [("preflight", preflight), ("capacity", capacity), ("benchmark", benchmark)]
    gen = [("pilot", lambda a: _generate_and_validate("pilot", a.plan_a, "stage7_pilot_A", "plan", a)),
           ("full_A", lambda a: _generate_and_validate("A", a.plan_a, "stage7_A", "plan", a)),
           ("B", lambda a: _generate_and_validate("B", a.plan_b, "stage7_B", "key", a)),
           ("C", lambda a: _generate_and_validate("C", a.plan_c, "stage7_C", "key", a))]
    phases = pre_gen + gen

    if args.dry_run:
        print("Stage 7 phases (dry run):")
        for name, _ in phases:
            print(f"  - {name}" + ("  [done]" if _marker(name).exists() else ""))
        print(f"Generation gate: {'OPEN (--approved-cells set)' if args.approved_cells else 'CLOSED (set --approved-cells to run pilot/A/B/C)'}")
        return 0

    MARKERS.mkdir(parents=True, exist_ok=True)
    for name, fn in phases:
        if _marker(name).exists():
            print(f"[skip] {name} (marker present)", flush=True)
            continue
        if name in {"pilot", "full_A", "B", "C"} and args.approved_cells is None:
            print("\nStopping before generation: obtain human approval of the prioritized cell list, "
                  "then re-run with --approved-cells <file>.")
            print("Resume: " + " ".join(sys.argv))
            return 0
        print(f"[run] {name}", flush=True)
        started = time.perf_counter()
        problems = fn(args)
        if problems:
            print(f"[FAIL] {name}: {problems}")
            print("Resume after fixing: " + " ".join(sys.argv))
            return 1
        _marker(name).write_text(json.dumps({"ok": True, "seconds": time.perf_counter() - started}), encoding="utf-8")
        print(f"[done] {name}", flush=True)
    print("\nStage 7 complete. Send the results/stage7/*.json reports for review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
