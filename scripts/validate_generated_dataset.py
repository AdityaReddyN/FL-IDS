"""Semantic validation of a generated Stage 1 run directory (read-only).

Human-run on real output; written and tested on synthetic fixtures. Reads the
eight Parquet tables + manifest against the cleaned source table and writes a
JSON pass/fail report. Checks (see nextSteps.md S7): schema/footers/counts/
SHA-256 vs manifest; attacked_rows 1:1 to source with orig == source and rows
outside accepted episodes unchanged; episodes inside one (icao24, segment_id),
non-overlapping, min-gap, every row eligible; ramp multipliers/positions and
the >=5 effective-row and no-op guards; injected displacement == multiplier x
parameter (constant), replay == earlier source rows, freeze == stored anchor;
windows recomputed from step labels; overlay_selections/segments/episodes
consistency and unique int64 ids; split membership; realized vs requested tau
with a binomial interval; per-family displacement quantiles (descriptive).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from flids.attacks.eligibility import REQUIRED_FIELDS, row_eligible  # noqa: E402
from flids.attacks.episode import HORIZONTAL_FAMILIES, REPLAY_FAMILIES  # noqa: E402
from flids.attacks.ramps import ramp_multipliers  # noqa: E402
from flids.attacks.schemas import FEATURE_FIELDS, TABLE_NAMES, validate_table  # noqa: E402
from flids.attacks.windows import label_windows  # noqa: E402

METRES_PER_DEGREE = 111_320.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _required(family: str, altitude_variant) -> tuple:
    if family in HORIZONTAL_FAMILIES:
        return REQUIRED_FIELDS["horizontal_manipulation"]
    if family == "freeze_fixed_value":
        return REQUIRED_FIELDS["freeze"]
    if family == "altitude_constant_deviation":
        return REQUIRED_FIELDS["altitude_manipulation_baro_plus_geo" if altitude_variant == "baro_plus_geo" else "altitude_manipulation"]
    return REQUIRED_FIELDS[family]


def _displacement_m(lat0, lon0, lat1, lon1):
    north = (np.asarray(lat1) - np.asarray(lat0)) * METRES_PER_DEGREE
    east = (np.asarray(lon1) - np.asarray(lon0)) * METRES_PER_DEGREE * np.cos(np.deg2rad(np.asarray(lat0)))
    return np.hypot(north, east)


def validate(run_dir: Path, source_path: Path, split_path: Path | None = None) -> dict:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    tables = {name: pd.read_parquet(run_dir / f"{name}.parquet") for name in TABLE_NAMES}
    source = pd.read_parquet(source_path).reset_index(drop=True)
    # source_row_id is the positional index of the cleaned table (as the
    # generator assigns it via add_natural_keys over the sorted source).
    source["source_row_id"] = np.arange(len(source), dtype=np.int64)
    checks: dict[str, dict] = {}

    def record(key, passed, **detail):
        checks[key] = {"passed": bool(passed), **detail}

    # (a) schema / counts / sha256 vs manifest.
    schema_ok, count_ok, sha_ok, problems = True, True, True, []
    for name in TABLE_NAMES:
        try:
            validate_table(tables[name], name)
        except Exception as error:  # noqa: BLE001
            schema_ok = False; problems.append(f"{name}: {error}")
        mrow = manifest["tables"][name]["row_count"]
        if len(tables[name]) != mrow:
            count_ok = False; problems.append(f"{name}: rows {len(tables[name])} != manifest {mrow}")
        if _sha256(run_dir / f"{name}.parquet") != manifest["tables"][name]["sha256"]:
            sha_ok = False; problems.append(f"{name}: sha256 mismatch")
    record("schema_counts_sha", schema_ok and count_ok and sha_ok, problems=problems[:10])

    attacked = tables["attacked_rows"].set_index("source_row_id", drop=False).sort_index()
    episodes = tables["episodes"]
    sid = attacked["source_row_id"].to_numpy()

    # (b) 1:1 to source; orig == source; metadata == source; non-episode rows unchanged.
    b_problems = []
    if attacked["source_row_id"].duplicated().any():
        b_problems.append("duplicate source_row_id")
    if sid.min() < 0 or sid.max() >= len(source) or len(attacked) != len(source):
        b_problems.append("attacked_rows not 1:1 with source")
    src = source.iloc[sid].reset_index(drop=True)
    at = attacked.reset_index(drop=True)
    for f in FEATURE_FIELDS:
        if not np.allclose(at[f"orig_{f}"].to_numpy(float), src[f].to_numpy(float), equal_nan=True):
            b_problems.append(f"orig_{f} != source")
    for meta in ("onground", "contact_lag_seconds", "contact_lag_missing"):
        a_m = at[meta].astype("object").where(at[meta].notna(), None).tolist()
        s_m = src[meta].astype("object").where(src[meta].notna(), None).tolist()
        if a_m != s_m:
            b_problems.append(f"metadata {meta} != source")
    non_ep = ~at["is_attack_row"].to_numpy(bool)
    for f in FEATURE_FIELDS:
        if not np.allclose(at.loc[non_ep, f"mod_{f}"].to_numpy(float), at.loc[non_ep, f"orig_{f}"].to_numpy(float), equal_nan=True):
            b_problems.append(f"non-episode mod_{f} != orig")
    record("source_one_to_one_and_unchanged", not b_problems, problems=b_problems[:10])

    # (c) episodes inside one segment; non-overlapping; min-gap; all rows eligible.
    c_problems = []
    min_gap = float(manifest.get("overlay_specs", [{}])[0].get("min_gap_seconds", 600.0)) if manifest.get("overlay_specs") else 600.0
    for (ic, seg), grp in episodes.groupby(["icao24", "segment_id"], sort=False):
        grp = grp.sort_values("start_time")
        ends = grp["end_time"].to_numpy()
        starts = grp["start_time"].to_numpy()
        if len(grp) > 1 and np.any(starts[1:] - ends[:-1] < min_gap):
            c_problems.append(f"{ic}/{seg}: episodes closer than {min_gap}s")
    # eligibility recompute on each episode's source rows.
    src_indexed = source.set_index(["icao24", "segment_id"], drop=False).sort_index()
    for row in episodes.itertuples():
        seg_rows = src_indexed.loc[[(row.icao24, row.segment_id)]]
        window = seg_rows.iloc[row.start_row_offset: row.start_row_offset + row.n_rows]
        mask = row_eligible(window, _required(row.attack_family, row.altitude_variant))
        if not mask.all():
            c_problems.append(f"episode {row.episode_id}: ineligible rows")
            break
    record("episodes_segment_gap_eligible", not c_problems, problems=c_problems[:10], min_gap_seconds=min_gap)

    # (d)+(e) ramp positions, >=5 effective, and injected effect per family.
    de_problems = []
    steps = tables["step_labels"].set_index("source_row_id")
    for row in episodes.itertuples():
        seg_rows = src_indexed.loc[[(row.icao24, row.segment_id)]]
        window = seg_rows.iloc[row.start_row_offset: row.start_row_offset + row.n_rows]
        src_ids = window["source_row_id"].to_numpy()
        mult, pos = ramp_multipliers(row.n_rows, 3, row.onset_mode)
        realized = mult.copy()
        if row.attack_family == "gradual_deviation":
            frac = np.ones(1) if row.n_rows == 1 else np.arange(row.n_rows) / (row.n_rows - 1)
            realized = mult * frac
        if int((realized >= 0.5).sum()) < 5:
            de_problems.append(f"episode {row.episode_id}: <5 effective rows")
        stored_pos = steps.loc[src_ids, "episode_position"].to_numpy()
        if not np.array_equal(stored_pos, pos):
            de_problems.append(f"episode {row.episode_id}: positions != ramps.py")
        ar = at.set_index("source_row_id").loc[src_ids]
        if row.attack_family == "constant_deviation":
            disp = _displacement_m(ar["orig_lat"], ar["orig_lon"], ar["mod_lat"], ar["mod_lon"])
            expected = realized * float(row.horizontal_magnitude_m)
            active = realized > 0
            if not np.allclose(disp[active], expected[active], rtol=0.05, atol=5.0):
                de_problems.append(f"episode {row.episode_id}: displacement != multiplier*magnitude")
        elif row.attack_family == "freeze_fixed_value" and row.freeze_anchor_source_row_id is not None and not pd.isna(row.freeze_anchor_source_row_id):
            anchor = source.iloc[int(row.freeze_anchor_source_row_id)]
            interior = realized >= 1.0
            if interior.any() and not (np.allclose(ar["mod_lat"].to_numpy()[interior], float(anchor["lat"]))
                                       and np.allclose(ar["mod_lon"].to_numpy()[interior], float(anchor["lon"]))):
                de_problems.append(f"episode {row.episode_id}: frozen rows != anchor")
        if len(de_problems) > 10:
            break
    record("ramp_effect_and_injection", not de_problems, problems=de_problems[:10])

    # (e-replay) replay rows equal the stored source rows.
    rep_problems = []
    rep = at[at["replay_source_row_id"].notna() & at["is_attack_row"]]
    for row in rep.itertuples():
        s = source.iloc[int(row.replay_source_row_id)]
        if not math.isclose(float(row.mod_lat), float(s["lat"]), rel_tol=0, abs_tol=1e-6):
            # full-field replay copies lat/lon from the source row at the stored delay
            if row.attack_family == "replay_full_field":
                rep_problems.append(f"source_row {row.source_row_id}: replay lat != stored source")
        if len(rep_problems) > 10:
            break
    record("replay_values_match_source", not rep_problems, problems=rep_problems[:10], replay_rows=int(len(rep)))

    # (f) windows recomputed from step labels.
    f_problems = []
    stored_windows = tables["windows"]
    sl = tables["step_labels"].merge(
        at[["source_row_id", "icao24", "segment_id", "segment_row_offset"]], on="source_row_id", how="left")
    recomputed = 0
    for _key, grp in sl.groupby(["icao24", "segment_id"], sort=False):
        grp = grp.sort_values("segment_row_offset")
        eids = grp["episode_id"].fillna(-1).to_numpy(np.int64)
        recomputed += len(label_windows(grp["ramp_multiplier"].to_numpy(float),
                                        grp["episode_position"].to_numpy(object), eids))
    if recomputed != len(stored_windows):
        f_problems.append(f"recomputed windows {recomputed} != stored {len(stored_windows)}")
    record("windows_recomputed", not f_problems, problems=f_problems, stored_windows=int(len(stored_windows)))

    # (g) overlay_selections / segments / episodes consistency.
    g_problems = []
    sel = tables["overlay_selections"]
    if (sel["selected"] & ~sel["eligible"]).any():
        g_problems.append("selected but not eligible")
    if (sel["chosen"] & ~sel["selected"]).any():
        g_problems.append("chosen but not selected")
    if episodes["episode_id"].duplicated().any():
        g_problems.append("duplicate episode_id")
    if tables["segments"][["icao24", "segment_id"]].duplicated().any():
        g_problems.append("duplicate segment rows")
    record("selection_consistency", not g_problems, problems=g_problems)

    # (h) split membership.
    h_problems = []
    if split_path and Path(split_path).exists():
        split = json.loads(Path(split_path).read_text(encoding="utf-8"))
        of = {str(ic): name for name, ids in split.items() for ic in ids}
        bad = [ic for ic, sp in zip(at["icao24"], at["split"]) if of.get(str(ic)) != sp]
        if bad:
            h_problems.append(f"{len(bad)} rows with split != split file")
    record("split_membership", not h_problems, problems=h_problems[:3], split_checked=bool(split_path))

    # (i) realized vs requested tau per overlay (binomial interval).
    tau_detail = {}
    for key, ov in manifest.get("overlays", {}).items():
        n = ov.get("eligible_segments", 0)
        requested = ov.get("tau_requested")
        realized = ov.get("realized_tau")
        if not n or requested is None:
            continue
        se = math.sqrt(max(requested * (1 - requested) / n, 0.0))
        within = abs((realized or 0.0) - requested) <= 3 * se + 1e-9
        tau_detail[key] = {"requested": requested, "realized": realized, "n_eligible": n, "within_3se": bool(within)}
    record("realized_tau_within_binomial", all(d["within_3se"] for d in tau_detail.values()) if tau_detail else True, by_overlay=tau_detail)

    # (j) per-family displacement quantiles (descriptive; always passes).
    quant = {}
    disp_all = _displacement_m(at["orig_lat"], at["orig_lon"], at["mod_lat"], at["mod_lon"])
    for fam, grp in at[at["is_attack_row"]].groupby("attack_family", sort=False):
        d = disp_all[grp.index.to_numpy()]
        d = d[np.isfinite(d)]
        if d.size:
            quant[str(fam)] = {q: float(np.quantile(d, v)) for q, v in (("q50", 0.5), ("q90", 0.9), ("q99", 0.99))}
    record("per_family_displacement_quantiles", True, quantiles=quant)

    return {"run_dir": str(run_dir), "source": str(source_path),
            "checks": checks, "passed": all(c["passed"] for c in checks.values())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--source", type=Path, default=Path("data/processed/opensky_clean_v1.parquet"))
    parser.add_argument("--split", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()
    report = validate(args.run_dir, args.source, args.split)
    out = args.report or (ROOT / "results" / f"validate_{args.run_dir.name}" / "report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True, default=float) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"],
                      "checks": {k: v["passed"] for k, v in report["checks"].items()}}, indent=2, sort_keys=True))
    print(f"Wrote {out}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
