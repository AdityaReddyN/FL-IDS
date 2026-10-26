"""Gate 1b oracle calibration on the cleaned HDD source (read-only, human-run).

Streams the cleaned parts one at a time (memory-bounded) and derives, from TRAIN
aircraft only, the train p95 residual thresholds and oracle recall sweeps. Writes
``results/gate1b_calibration_v2.json`` and prints a tier proposal; it changes no
YAML and never overwrites ``docs/calibration_v3_stage1.json``.

Covers: (1) horizontal boundary recall vs magnitude for abrupt and the real ramp
(first step 0.25x) per speed band, with a tier proposal at ~10/30/60/90% for the
fast bands and a gross control; (2) integrated-residual oracle (k=5,10,29);
(3) partial-replay oracle (boundary vs interior); (4) altitude oracle per
vertical-rate band (baro/geo), 15+ band separated; (5) oracle FPR on matched
controls + residual quantiles; (6) per-overlay capacity per split x speed band x
unique aircraft. Sampling uses a seeded reservoir, so results are deterministic.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from flids.attacks.calibration import (  # noqa: E402
    FAST_BANDS, RAMP_FIRST_STEP_FRACTION, SPEED_BANDS, VERTICAL_BANDS, Reservoir,
    altitude_residual_m, band_label, freeze_recall, horizontal_components,
    manipulation_recall, propose_tiers_by_recall, residual_m,
)
from flids.data.clean import FEATURES  # noqa: E402

SPLIT_NAMES = ("train", "val", "test")
# Finer grid through the fast-band transitions (100-200 recall climbs over
# 1000-2000 m; 200_plus over 2000-4000 m), so tiers can be placed at the
# ~10/30/60/90% boundary-recall targets.
MAGNITUDES = (
    500.0, 1000.0, 1200.0, 1400.0, 1600.0, 1800.0, 2000.0, 2200.0, 2500.0,
    2800.0, 3200.0, 3600.0, 4000.0, 5000.0, 6000.0, 8000.0, 12000.0, 16000.0,
)
GROSS_CONTROL_M = 16000.0
ALT_TIER_SHIFTS = {"subtle": 60.0, "moderate": 125.0, "blatant": 300.0}
MAX_CONTACT_LAG_SECONDS = 30.0
REPLAY_DELAY_S = 300.0
REPLAY_TOLERANCE_S = 5.0
EPISODE_ROWS = {"nominal_120s": 12, "long_600s": 60, "long_900s": 90}


def _quantiles(values, levels=(0.5, 0.9, 0.95, 0.99)) -> dict:
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"n": 0}
    return {"n": int(v.size), **{f"q{int(l*100)}": float(np.quantile(v, l)) for l in levels}}


def process_part(df, horiz, replay_res, alt, capacity):
    df = df.sort_values(["icao24", "segment_id", "time"], kind="mergesort").reset_index(drop=True)
    icao = df["icao24"].astype(str).to_numpy()
    seg = df["segment_id"].to_numpy()
    time = df["time"].to_numpy(float)
    lat = df["lat"].to_numpy(float); lon = df["lon"].to_numpy(float)
    vel = df["velocity"].to_numpy(float); head = df["heading"].to_numpy(float)
    vrate = df["vertrate"].to_numpy(float)
    baro = df["baroaltitude"].to_numpy(float); geo = df["geoaltitude"].to_numpy(float)
    onground = df["onground"]
    airborne = ~onground.fillna(True).astype("boolean").astype(bool).to_numpy() if str(onground.dtype) == "boolean" \
        else ~onground.fillna(True).astype(bool).to_numpy()
    lag = df["contact_lag_seconds"].to_numpy(float)
    observed = df[list(FEATURES)].notna().all(axis=1).to_numpy()
    eligible = airborne & np.isfinite(lag) & (lag >= 0.0) & (lag <= MAX_CONTACT_LAG_SECONDS) & observed
    split_label = pd.Series(icao).map(capacity["_split_of"]).to_numpy()
    is_train = split_label == "train"

    # Group id per (icao24, segment_id); the frame is sorted so it is monotonic.
    n = len(df)
    new_group = np.ones(n, dtype=bool)
    new_group[1:] = (icao[1:] != icao[:-1]) | (seg[1:] != seg[:-1])
    gid = (np.cumsum(new_group) - 1).astype(np.int64)
    same_seg = ~new_group
    prev = np.arange(n) - 1
    dt = np.where(same_seg, time - time[prev], np.nan)
    pair = same_seg & eligible & eligible[prev] & (dt > 0) & (dt <= 30.0)

    north, east, en, ee = horizontal_components(lat[prev], lon[prev], lat, lon, vel, head, dt)
    resid = residual_m(north, east, en, ee)
    sband = band_label(vel, SPEED_BANDS)

    p = pair
    horiz.add({"resid": resid[p], "vel": vel[p], "band": sband[p], "north": north[p],
               "east": east[p], "en": en[p], "ee": ee[p], "dt": dt[p], "train": is_train[p]})

    # Altitude pairs.
    alt_valid = pair & np.isfinite(baro[prev]) & np.isfinite(geo[prev])
    vband = band_label(np.abs(vrate), VERTICAL_BANDS)
    av = alt_valid
    alt.add({"baro": altitude_residual_m(baro[prev][av], baro[av], vrate[av], dt[av]),
             "geo": altitude_residual_m(geo[prev][av], geo[av], vrate[av], dt[av]),
             "vband": vband[av], "train": is_train[av]})

    # --- Vectorized partial replay: within-group ~300 s-earlier eligible link.
    # A sort key of gid*OFFSET + time keeps nearest-neighbour search inside one
    # group (OFFSET exceeds any epoch time, so groups never overlap in key space).
    OFFSET = 4_000_000_000
    key = gid * OFFSET + time.astype(np.int64)
    src = np.flatnonzero(eligible)
    if src.size:
        src_key = key[src]
        desired_key = key - int(REPLAY_DELAY_S)
        right = np.clip(np.searchsorted(src_key, desired_key, side="left"), 0, src.size - 1)
        left = np.clip(right - 1, 0, src.size - 1)
        pick = np.where(np.abs(src_key[right] - desired_key) < np.abs(src_key[left] - desired_key), right, left)
        picked = src[pick]
        desired_time = time - REPLAY_DELAY_S
        ok = (gid[picked] == gid) & (np.abs(time[picked] - desired_time) <= REPLAY_TOLERANCE_S) & (time[picked] < time)
        rp = pair & ok
        if rp.any():
            sn = (lat[picked] - lat) * 111_320.0
            se = (lon[picked] - lon) * 111_320.0 * np.cos(np.deg2rad(lat))
            replay_res.add({"north": north[rp], "east": east[rp], "en": en[rp], "ee": ee[rp],
                            "sn": sn[rp], "se": se[rp], "band": sband[rp], "train": is_train[rp]})

    # --- Vectorized episode-start capacity per split x speed band.
    elig_prefix = np.concatenate([[0], np.cumsum(eligible, dtype=np.int64)])
    gstart_prefix = np.concatenate([[0], np.cumsum(new_group.astype(np.int64))])
    for label, ep in EPISODE_ROWS.items():
        if n < ep:
            continue
        i = np.arange(n - ep + 1)
        all_eligible = (elig_prefix[i + ep] - elig_prefix[i]) == ep
        single_segment = (gstart_prefix[i + ep] - gstart_prefix[i + 1]) == 0
        starts = i[all_eligible & single_segment]
        if starts.size == 0:
            continue
        frame = pd.DataFrame({"split": split_label[starts], "band": sband[starts], "icao": icao[starts]})
        frame = frame[frame["split"].isin(SPLIT_NAMES)]
        for (split, band), group in frame.groupby(["split", "band"], sort=False):
            cell = capacity[label].setdefault(split, {}).setdefault(band, {"episode_starts": 0, "aircraft": set()})
            cell["episode_starts"] += int(len(group))
            cell["aircraft"].update(group["icao"].unique().tolist())


def summarize(horiz, replay_res, alt, capacity, seed) -> dict:
    h = horiz.arrays()
    rng = np.random.default_rng(seed)
    train = h["train"].astype(bool)
    # Train p95 thresholds per speed band; per-band threshold vector for recall.
    thresholds = {}
    for name, _, _ in SPEED_BANDS:
        band_tr = h["resid"][train & (h["band"] == name)]
        thresholds[name] = float(np.quantile(band_tr, 0.95)) if band_tr.size else None

    # Horizontal recall sweeps (all-split sampled pairs; band threshold).
    manip = {"abrupt": {}, "real_ramp": {}}
    fpr = {}
    tier_proposal = {}
    for name, _, _ in SPEED_BANDS:
        sel = h["band"] == name
        thr = thresholds[name]
        if thr is None or not sel.any():
            continue
        north, east, en, ee = h["north"][sel], h["east"][sel], h["en"][sel], h["ee"][sel]
        bearings = rng.uniform(0, 2 * np.pi, size=north.size)
        thr_vec = np.full(north.size, thr)
        for onset, frac in (("abrupt", 1.0), ("real_ramp", RAMP_FIRST_STEP_FRACTION)):
            recalls = [manipulation_recall(north, east, en, ee, thr_vec, m, bearings, frac) for m in MAGNITUDES]
            manip[onset][name] = {str(int(m)): r for m, r in zip(MAGNITUDES, recalls)}
            if onset == "abrupt" and name in FAST_BANDS:
                tier_proposal[name] = propose_tiers_by_recall(MAGNITUDES, recalls)
        fpr[name] = float((residual_m(north, east, en, ee) >= thr).mean())
    gross = {}
    for name, _, _ in SPEED_BANDS:
        sel = h["band"] == name
        thr = thresholds[name]
        if thr is None or not sel.any():
            continue
        bearings = rng.uniform(0, 2 * np.pi, size=int(sel.sum()))
        gross[name] = manipulation_recall(h["north"][sel], h["east"][sel], h["en"][sel], h["ee"][sel],
                                          np.full(int(sel.sum()), thr), GROSS_CONTROL_M, bearings, 1.0)

    # Freeze and integrated-residual oracle (single-step proxy per band).
    freeze = {}
    for name, _, _ in SPEED_BANDS:
        sel = h["band"] == name
        thr = thresholds[name]
        if thr is None or not sel.any():
            continue
        freeze[name] = {
            onset: freeze_recall(h["north"][sel], h["east"][sel], h["en"][sel], h["ee"][sel],
                                 np.full(int(sel.sum()), thr), frac)
            for onset, frac in (("abrupt", 0.0), ("real_ramp", RAMP_FIRST_STEP_FRACTION))
        }

    # Partial replay recall.
    r = replay_res.arrays()
    partial = {}
    if r:
        rtrain = r["train"].astype(bool)
        for name, _, _ in SPEED_BANDS:
            sel = r["band"] == name
            thr = thresholds.get(name)
            if thr is None or not sel.any():
                continue
            onset_results = {}
            for onset, frac in (("abrupt", 1.0), ("real_ramp", RAMP_FIRST_STEP_FRACTION)):
                inj = residual_m(r["north"][sel] + frac * r["sn"][sel], r["east"][sel] + frac * r["se"][sel],
                                 r["en"][sel], r["ee"][sel])
                onset_results[onset] = float((inj >= thr).mean())
            partial[name] = onset_results

    # Altitude oracle per vertical band.
    a = alt.arrays()
    altitude = {}
    if a:
        atrain = a["train"].astype(bool)
        for channel in ("baro", "geo"):
            altitude[channel] = {}
            for vb, _, _ in VERTICAL_BANDS:
                vals = a[channel][atrain & (a["vband"] == vb)]
                thr = float(np.quantile(vals, 0.95)) if vals.size else None
                tiers = {t: (float((s >= thr)) if thr is not None else None) for t, s in ALT_TIER_SHIFTS.items()}
                altitude[channel][vb] = {"train_p95_residual_m": thr, "n": int(vals.size),
                                         "tier_shift_detected": tiers,
                                         "separate_or_exclude": vb == "15_plus"}

    # Capacity table (convert aircraft sets to counts).
    capacity_out = {}
    for label in EPISODE_ROWS:
        capacity_out[label] = {}
        for split in SPLIT_NAMES:
            bands = capacity.get(label, {}).get(split, {})
            capacity_out[label][split] = {
                b: {"episode_starts": cell["episode_starts"], "unique_aircraft": len(cell["aircraft"]),
                    "descriptive_only_if_under_100_aircraft": bool(split == "test" and len(cell["aircraft"]) < 100)}
                for b, cell in bands.items()
            }

    return {
        "report_version": "gate1b_v2",
        "detector": "train_split_speed_band_p95_horizontal_residual",
        "ramp_first_step_fraction": RAMP_FIRST_STEP_FRACTION,
        "sampled_pairs": int(h["resid"].size), "sampled_pairs_seen": int(horiz.seen),
        "speed_band_train_p95_threshold_m": thresholds,
        "horizontal_residual_quantiles_m": {name: _quantiles(h["resid"][h["band"] == name]) for name, _, _ in SPEED_BANDS},
        "manipulation_recall_by_magnitude": manip,
        "gross_control_abrupt_recall": gross,
        "tier_proposal_fast_bands_abrupt": tier_proposal,
        "freeze_recall": freeze,
        "partial_replay_recall": partial,
        "altitude_oracle": altitude,
        "oracle_fpr_on_matched_controls": fpr,
        "per_overlay_capacity_by_split_speed_band": capacity_out,
        "note": "Read-only. Thresholds from TRAIN aircraft only. No YAML changed; "
                "parameters are re-approved in a new decision before generation.",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean-dir", type=Path, default=Path("data/processed/hdd_clean_v1"))
    parser.add_argument("--out", type=Path, default=Path("results/gate1b_calibration_v2.json"))
    parser.add_argument("--reservoir", type=int, default=3_000_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-parts", type=int, default=None,
                        help="process only the first N parts (smoke test; thresholds are then partial)")
    return parser.parse_args()


def run(clean_dir: Path, reservoir: int, seed: int, max_parts: int | None = None) -> dict:
    split = json.loads((clean_dir / "split_aircraft.json").read_text(encoding="utf-8"))
    split_of = {str(ic): name for name, ids in split.items() for ic in ids}
    horiz = Reservoir(reservoir, seed)
    replay_res = Reservoir(reservoir, seed + 1)
    alt = Reservoir(reservoir, seed + 2)
    capacity: dict = {label: {} for label in EPISODE_ROWS}
    capacity["_split_of"] = split_of
    parts = sorted(clean_dir.glob("part_*.parquet"))
    if not parts:
        raise SystemExit(f"no part_*.parquet in {clean_dir}")
    if max_parts is not None:
        parts = parts[:max_parts]
    for part in parts:
        df = pd.read_parquet(part, columns=["icao24", "segment_id", "time", "onground",
                                            "contact_lag_seconds", *FEATURES])
        process_part(df, horiz, replay_res, alt, capacity)
        print(f"processed {part.name}", flush=True)
    capacity.pop("_split_of", None)
    return summarize(horiz, replay_res, alt, capacity, seed)


def main() -> int:
    args = parse_args()
    clean_dir = args.clean_dir if args.clean_dir.is_absolute() else ROOT / args.clean_dir
    out = args.out if args.out.is_absolute() else ROOT / args.out
    if out.name == "calibration_v3_stage1.json" or "docs" in out.parts:
        raise SystemExit("refusing to write under docs/ or over calibration_v3_stage1.json")
    report = run(clean_dir, args.reservoir, args.seed, args.max_parts)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"thresholds": report["speed_band_train_p95_threshold_m"],
                      "tier_proposal": report["tier_proposal_fast_bands_abrupt"],
                      "fpr": report["oracle_fpr_on_matched_controls"]}, indent=2, sort_keys=True))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
