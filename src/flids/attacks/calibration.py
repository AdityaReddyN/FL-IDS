"""Pure oracle-calibration helpers (Gate 1b).

These mirror the horizontal/altitude residual and oracle-recall formulas of
``scripts/calibrate_v3_stage1.py`` (the approved report_version 4 methodology)
with one deliberate change for the HDD v2 calibration: the REAL ramp onset uses
a first-step fraction of 0.25 (``RAMP_FIRST_STEP_FRACTION``) rather than 1/3.
Thresholds are the train-only p95 of the per-pair residual within a speed band;
the oracle "detects" an injected displacement when the resulting residual meets
the band threshold.

Everything here is pure and unit-tested on tiny synthetic arrays; the streaming,
train-only driver over the cleaned HDD parts lives in
``scripts/gate1b_calibration.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

METRES_PER_DEGREE = 111_320.0
RAMP_FIRST_STEP_FRACTION = 0.25  # real ramp first step = 0.25 * magnitude (S6)
SPEED_BANDS: tuple[tuple[str, float, float], ...] = (
    ("0_50", 0.0, 50.0), ("50_100", 50.0, 100.0),
    ("100_200", 100.0, 200.0), ("200_plus", 200.0, np.inf),
)
VERTICAL_BANDS: tuple[tuple[str, float, float], ...] = (
    ("0_5", 0.0, 5.0), ("5_15", 5.0, 15.0), ("15_plus", 15.0, np.inf),
)
FAST_BANDS: tuple[str, ...] = ("100_200", "200_plus")
RECALL_TARGETS: tuple[float, ...] = (0.10, 0.30, 0.60, 0.90)


def band_label(values, bands: tuple[tuple[str, float, float], ...]) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    out = np.full(values.shape, "outside", dtype=object)
    for name, lower, upper in bands:
        out[(values >= lower) & (values < upper)] = name
    return out


def horizontal_components(prev_lat, prev_lon, lat, lon, velocity, heading_deg, dt):
    """North/east displacement and the velocity/heading-implied expectation (metres).

    Matches ``calibrate_v3_stage1.py``: ``expected = velocity * dt`` using the
    current row's reported velocity and heading. Longitude uses a simple scaled
    delta (not antimeridian-wrapped), as in that script.
    """
    prev_lat = np.asarray(prev_lat, float); prev_lon = np.asarray(prev_lon, float)
    lat = np.asarray(lat, float); lon = np.asarray(lon, float)
    velocity = np.asarray(velocity, float); heading_deg = np.asarray(heading_deg, float)
    dt = np.asarray(dt, float)
    north = (lat - prev_lat) * METRES_PER_DEGREE
    east = (lon - prev_lon) * METRES_PER_DEGREE * np.cos(np.deg2rad((lat + prev_lat) / 2.0))
    expected = velocity * dt
    expected_north = expected * np.cos(np.deg2rad(heading_deg))
    expected_east = expected * np.sin(np.deg2rad(heading_deg))
    return north, east, expected_north, expected_east


def residual_m(north, east, expected_north, expected_east) -> np.ndarray:
    return np.hypot(np.asarray(north) - np.asarray(expected_north),
                    np.asarray(east) - np.asarray(expected_east))


def altitude_residual_m(prev_alt, alt, vertrate, dt) -> np.ndarray:
    """|observed altitude change - vertical-rate-implied change| (metres)."""
    return np.abs((np.asarray(alt, float) - np.asarray(prev_alt, float))
                  - np.asarray(vertrate, float) * np.asarray(dt, float))


def manipulation_recall(north, east, expected_north, expected_east, threshold,
                        magnitude, bearings, onset_fraction) -> float:
    """Oracle recall for a constant horizontal offset of ``magnitude`` metres.

    ``onset_fraction`` is 1.0 for abrupt onset and
    :data:`RAMP_FIRST_STEP_FRACTION` for the real ramp's first step. ``bearings``
    are per-sample radians. Detects when the injected residual >= threshold.
    """
    shift = onset_fraction * float(magnitude)
    injected = residual_m(
        np.asarray(north) + shift * np.cos(bearings),
        np.asarray(east) + shift * np.sin(bearings),
        expected_north, expected_east,
    )
    return float((injected >= np.asarray(threshold)).mean()) if injected.size else None


def freeze_recall(north, east, expected_north, expected_east, threshold, onset_fraction) -> dict:
    """Oracle recall for a freeze: position held, so displacement is scaled down."""
    onset = residual_m(onset_fraction * np.asarray(north), onset_fraction * np.asarray(east),
                       expected_north, expected_east)
    interior = np.hypot(np.asarray(expected_north), np.asarray(expected_east))
    thr = np.asarray(threshold)
    return {
        "onset_step_recall": float((onset >= thr).mean()) if onset.size else None,
        "interior_step_recall": float((interior >= thr).mean()) if interior.size else None,
    }


def integrated_residual_m(north_steps, east_steps, expected_north_steps, expected_east_steps) -> float:
    """Residual of the summed displacement vs summed expectation over k steps."""
    dn = np.sum(np.asarray(north_steps, float)) - np.sum(np.asarray(expected_north_steps, float))
    de = np.sum(np.asarray(east_steps, float)) - np.sum(np.asarray(expected_east_steps, float))
    return float(np.hypot(dn, de))


def propose_tiers_by_recall(magnitudes, recalls, targets: tuple[float, ...] = RECALL_TARGETS) -> dict:
    """For each target recall, the smallest magnitude whose recall >= target.

    ``recalls`` need not be perfectly monotone; the smallest qualifying magnitude
    is chosen. Returns ``{target: magnitude or None}``.
    """
    mags = np.asarray(magnitudes, float)
    rec = np.asarray(recalls, float)
    order = np.argsort(mags)
    mags, rec = mags[order], rec[order]
    out = {}
    for target in targets:
        hit = np.flatnonzero(rec >= target)
        out[f"recall_{int(target * 100)}pct"] = float(mags[hit[0]]) if hit.size else None
    return out


@dataclass
class Reservoir:
    """Vectorized, seeded uniform reservoir over parallel named arrays.

    Each row gets a random key in [0, 1); the ``capacity`` rows with the
    smallest keys are kept. This yields a uniform sample of size ``capacity``
    from the full stream regardless of chunk boundaries, with bounded memory,
    and is fast (no per-row Python loop).
    """

    capacity: int
    seed: int = 42
    _store: dict[str, np.ndarray] = field(default_factory=dict)
    _keys: np.ndarray = field(default_factory=lambda: np.empty(0))
    _seen: int = 0
    _rng: np.random.Generator | None = None

    def __post_init__(self):
        self._rng = np.random.default_rng(self.seed)

    def add(self, columns: dict[str, np.ndarray]) -> None:
        n = 0 if not columns else len(next(iter(columns.values())))
        if n == 0:
            return
        self._seen += n
        new_keys = self._rng.random(n)
        if not self._store:
            self._store = {k: np.asarray(v) for k, v in columns.items()}
            self._keys = new_keys
        else:
            self._keys = np.concatenate([self._keys, new_keys])
            for k in self._store:
                self._store[k] = np.concatenate([self._store[k], np.asarray(columns[k])])
        if self._keys.size > self.capacity:
            keep = np.argpartition(self._keys, self.capacity)[: self.capacity]
            self._keys = self._keys[keep]
            for k in self._store:
                self._store[k] = self._store[k][keep]

    def arrays(self) -> dict[str, np.ndarray]:
        return {k: np.asarray(v) for k, v in self._store.items()}

    @property
    def seen(self) -> int:
        return self._seen
