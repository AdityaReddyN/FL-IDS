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
MAGNITUDES = (500.0, 1000.0, 2000.0, 4000.0, 6000.0, 8000.0, 12000.0, 16000.0)
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


def _replay_shift(times, lat, lon, eligible):
    """Per-segment 300 s-earlier same-track link; returns shift north/east or NaN."""
    n = times.size
    sn = np.full(n, np.nan); se = np.full(n, np.nan)
    src_pos = np.flatnonzero(eligible)
    if src_pos.size == 0:
        return sn, se
    src_t = times[src_pos].astype(float)
    desired = times.astype(float) - REPLAY_DELAY_S
    right = np.searchsorted(src_t, desired, side="left")
    left = np.clip(right - 1, 0, src_pos.size - 1)
    right = np.clip(right, 0, src_pos.size - 1)
    picked = np.where(np.abs(src_t[right] - desired) < np.abs(src_t[left] - desired), right, left)
    dist = np.abs(src_t[picked] - desired)
    ok = (dist <= REPLAY_TOLERANCE_S) & (src_t[picked] < times)
    s = src_pos[picked]
    sn[ok] = (lat[s[ok]] - lat[ok]) * 111_320.0
    se[ok] = (lon[s[ok]] - lon[ok]) * 111_320.0 * np.cos(np.deg2rad(lat[ok]))
    return sn, se


def process_part(df, train_ids, horiz, replay_res, alt, capacity):
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
    is_train = np.isin(icao, np.asarray(list(train_ids)))

    # Within (icao24, segment_id): previous-row arrays.
    same_seg = np.zeros(len(df), dtype=bool)
    same_seg[1:] = (icao[1:] == icao[:-1]) & (seg[1:] == seg[:-1])
    prev = np.arange(len(df)) - 1
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

    # One pass over segments: collect partial-replay rows (added to the
    # reservoir ONCE per part, not per segment, to avoid O(n^2) concatenation)
    # and accumulate episode-start capacity.
    rep: dict[str, list] = {k: [] for k in ("north", "east", "en", "ee", "sn", "se", "band", "train")}
    segment_indices = df.groupby(["icao24", "segment_id"], sort=False).indices
    for (ic, _sg), pos in segment_indices.items():
        pos = np.asarray(pos, dtype=np.int64)
        if pos.size < 2:
            continue
        ic = str(ic)
        sn, se = _replay_shift(time[pos], lat[pos], lon[pos], eligible[pos])
        rp = pair[pos] & np.isfinite(sn)
        if rp.any():
            local = pos[rp]
            rep["north"].append(north[local]); rep["east"].append(east[local])
            rep["en"].append(en[local]); rep["ee"].append(ee[local])
            rep["sn"].append(sn[rp]); rep["se"].append(se[rp])
            rep["band"].append(sband[local]); rep["train"].append(is_train[local])
        split = "train" if ic in train_ids else capacity["_split_of"].get(ic)
        if split is None:
            continue
        prefix = np.r_[0, np.cumsum(eligible[pos], dtype=np.int64)]
        bands_at = sband[pos]
        for label, ep in EPISODE_ROWS.items():
            if pos.size < ep:
                continue
            starts = np.flatnonzero(prefix[ep:] - prefix[:-ep] == ep)
            if starts.size == 0:
                continue
            bands = bands_at[starts]
            for bname, _, _ in SPEED_BANDS:
                k = int(np.count_nonzero(bands == bname))
                if k == 0:
                    continue
                cell = capacity[label].setdefault(split, {}).setdefault(bname, {"episode_starts": 0, "aircraft": set()})
                cell["episode_starts"] += k
                cell["aircraft"].add(ic)
    if rep["north"]:
        replay_res.add({k: np.concatenate(v) for k, v in rep.items()})


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
    train_ids = set(map(str, split["train"]))
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
        process_part(df, train_ids, horiz, replay_res, alt, capacity)
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
