import importlib.util
from pathlib import Path

import numpy as np
import pytest

from flids.attacks.kinematics import pair_residual_m, speed_band

ROOT = Path(__file__).resolve().parents[1]


def load_calibration_module():
    spec = importlib.util.spec_from_file_location(
        "calibrate_v3_stage1", ROOT / "scripts" / "calibrate_v3_stage1.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def calibration_residual_reference(
    lat_i, lon_i, lat_j, lon_j, velocity_i, heading_i_deg, dt_s
):
    """Mirror of scripts/calibrate_v3_stage1.py lines 415--419."""
    north = (lat_j - lat_i) * 111_320.0
    east = (lon_j - lon_i) * 111_320.0 * np.cos(
        np.deg2rad((lat_i + lat_j) / 2.0)
    )
    expected = velocity_i * dt_s
    expected_north = expected * np.cos(np.deg2rad(heading_i_deg))
    expected_east = expected * np.sin(np.deg2rad(heading_i_deg))
    return np.hypot(north - expected_north, east - expected_east)


def test_speed_band_scalar_boundaries() -> None:
    assert speed_band(0.0) == "0_50"
    assert speed_band(49.999) == "0_50"
    assert speed_band(50.0) == "50_100"
    assert speed_band(99.999) == "50_100"
    assert speed_band(100.0) == "100_200"
    assert speed_band(199.999) == "100_200"
    assert speed_band(200.0) == "200_plus"
    assert speed_band(613.0) == "200_plus"


def test_speed_band_missing_and_invalid() -> None:
    assert speed_band(np.nan) == "missing"
    assert speed_band(-0.1) == "invalid"


def test_speed_band_is_vectorized_and_matches_calibration() -> None:
    calibration = load_calibration_module()
    values = np.array([0.0, 10.0, 49.99, 50.0, 99.99, 100.0, 199.99, 200.0, 613.0])
    expected = calibration.band_labels(values, calibration.SPEED_BANDS)
    result = speed_band(values)
    assert isinstance(result, np.ndarray)
    np.testing.assert_array_equal(result, expected)


def test_speed_band_vector_missing_and_invalid() -> None:
    values = np.array([np.nan, -1.0, 0.0, 200.0])
    np.testing.assert_array_equal(
        speed_band(values), np.array(["missing", "invalid", "0_50", "200_plus"])
    )


def test_pair_residual_matches_calibration_formula() -> None:
    calibration = load_calibration_module()
    points = [
        (10.0, 20.0, 10.05, 20.07, 120.0, 35.0, 8.0),
        (45.0, -3.0, 44.98, -3.02, 80.0, 300.0, 12.0),
        (-20.0, 100.0, -20.01, 100.03, 250.0, 180.0, 4.0),
    ]
    for point in points:
        observed = pair_residual_m(*point)
        expected = calibration_residual_reference(*point)
        assert observed == pytest.approx(float(expected), rel=1e-12, abs=1e-9)
    assert calibration is not None


def test_pair_residual_zero_for_straight_constant_velocity() -> None:
    lat_i, lon_i = 10.0, 20.0
    velocity, heading, dt = 100.0, 90.0, 10.0
    dlon = (velocity * dt) / (111_320.0 * np.cos(np.deg2rad(lat_i)))
    residual = pair_residual_m(
        lat_i, lon_i, lat_i, lon_i + dlon, velocity, heading, dt
    )
    assert residual == pytest.approx(0.0, abs=1e-6)


def test_pair_residual_large_for_offset() -> None:
    lat_i, lon_i = 10.0, 20.0
    velocity, heading, dt = 100.0, 90.0, 10.0
    dlon = (velocity * dt) / (111_320.0 * np.cos(np.deg2rad(lat_i)))
    residual = pair_residual_m(
        lat_i, lon_i, lat_i, lon_i + dlon + 0.01, velocity, heading, dt
    )
    assert residual > 1_000.0


def test_heading_convention_north_and_east() -> None:
    dt = 10.0
    north_dlat = (100.0 * dt) / 111_320.0
    assert pair_residual_m(10.0, 20.0, 10.0 + north_dlat, 20.0, 100.0, 0.0, dt) == pytest.approx(0.0, abs=1e-6)

    east_dlon = (100.0 * dt) / (111_320.0 * np.cos(np.deg2rad(10.0)))
    assert pair_residual_m(10.0, 20.0, 10.0, 20.0 + east_dlon, 100.0, 90.0, dt) == pytest.approx(0.0, abs=1e-6)


def test_pair_residual_wraps_antimeridian() -> None:
    residual = pair_residual_m(10.0, 179.9, 10.0, -179.9, 0.0, 0.0, 1.0)
    expected = 0.2 * 111_320.0 * np.cos(np.deg2rad(10.0))
    assert residual == pytest.approx(expected, rel=1e-9)
    assert residual < 25_000.0
