"""Tests for the pure Gate 1b calibration helpers (S6)."""

import numpy as np

from flids.attacks.calibration import (
    RAMP_FIRST_STEP_FRACTION,
    Reservoir,
    altitude_residual_m,
    band_label,
    freeze_recall,
    horizontal_components,
    integrated_residual_m,
    manipulation_recall,
    propose_tiers_by_recall,
    residual_m,
)
from flids.attacks.calibration import SPEED_BANDS, VERTICAL_BANDS


def test_horizontal_components_zero_residual_for_consistent_motion():
    # One step due north at 100 m/s for 10 s -> 1000 m north, residual 0.
    dlat = 1000.0 / 111_320.0
    north, east, en, ee = horizontal_components(
        prev_lat=0.0, prev_lon=0.0, lat=dlat, lon=0.0,
        velocity=100.0, heading_deg=0.0, dt=10.0,
    )
    assert abs(residual_m(north, east, en, ee)) < 1e-6


def test_manipulation_recall_increases_with_magnitude():
    # Zero-baseline motion (stationary expectation), so injected magnitude drives it.
    north = np.zeros(1000); east = np.zeros(1000)
    en = np.zeros(1000); ee = np.zeros(1000)
    threshold = np.full(1000, 500.0)
    bearings = np.zeros(1000)
    small = manipulation_recall(north, east, en, ee, threshold, 300.0, bearings, 1.0)
    large = manipulation_recall(north, east, en, ee, threshold, 5000.0, bearings, 1.0)
    assert small == 0.0 and large == 1.0


def test_abrupt_recall_at_least_ramp_recall():
    rng = np.random.default_rng(0)
    north = rng.normal(0, 50, 2000); east = rng.normal(0, 50, 2000)
    en = np.zeros(2000); ee = np.zeros(2000)
    threshold = np.full(2000, 800.0)
    bearings = rng.uniform(0, 2 * np.pi, 2000)
    abrupt = manipulation_recall(north, east, en, ee, threshold, 2500.0, bearings, 1.0)
    ramp = manipulation_recall(north, east, en, ee, threshold, 2500.0, bearings, RAMP_FIRST_STEP_FRACTION)
    assert abrupt >= ramp


def test_freeze_interior_recall_uses_velocity_times_dt():
    # Expected displacement 1500 m; interior freeze residual == 1500 >= 800 -> recall 1.
    en = np.full(10, 1500.0); ee = np.zeros(10)
    north = np.full(10, 1500.0); east = np.zeros(10)
    rec = freeze_recall(north, east, en, ee, np.full(10, 800.0), onset_fraction=0.25)
    assert rec["interior_step_recall"] == 1.0


def test_integrated_residual_sums_steps():
    north = [100, 100, 100]; east = [0, 0, 0]
    en = [10, 10, 10]; ee = [0, 0, 0]
    assert abs(integrated_residual_m(north, east, en, ee) - 270.0) < 1e-9


def test_altitude_residual_and_bands():
    assert altitude_residual_m(3000.0, 3100.0, 5.0, 10.0) == 50.0  # |100 - 50|
    labels = band_label([1.0, 7.0, 20.0], VERTICAL_BANDS)
    assert list(labels) == ["0_5", "5_15", "15_plus"]
    sb = band_label([10.0, 150.0, 300.0], SPEED_BANDS)
    assert list(sb) == ["0_50", "100_200", "200_plus"]


def test_propose_tiers_picks_smallest_qualifying_magnitude():
    mags = [500, 1000, 2000, 4000, 8000, 16000]
    recalls = [0.05, 0.2, 0.35, 0.65, 0.92, 0.99]
    tiers = propose_tiers_by_recall(mags, recalls)
    assert tiers["recall_10pct"] == 1000.0
    assert tiers["recall_30pct"] == 2000.0
    assert tiers["recall_60pct"] == 4000.0
    assert tiers["recall_90pct"] == 8000.0


def test_reservoir_is_bounded_uniform_and_seed_deterministic():
    a = Reservoir(capacity=1000, seed=7)
    b = Reservoir(capacity=1000, seed=7)
    for start in range(0, 100_000, 10_000):
        chunk = {"x": np.arange(start, start + 10_000, dtype=float)}
        a.add(chunk)
        b.add(chunk)
    xa = a.arrays()["x"]
    assert xa.size == 1000
    assert a.seen == 100_000
    # Deterministic for a fixed seed; uniform coverage across the full range.
    assert np.array_equal(np.sort(xa), np.sort(b.arrays()["x"]))
    assert xa.min() < 10_000 and xa.max() > 90_000
