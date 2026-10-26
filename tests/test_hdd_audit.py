"""Tests for the pure HDD-audit helpers and the streaming reader (S3)."""

import io
import tarfile

import numpy as np
import pytest

from flids.data.hdd_audit import (
    EXPECTED_COLUMNS,
    aircraft_recurrence,
    cadence_shares,
    cell_coverage,
    column_schema_diff,
    dt_quantiles,
    resample_count_estimate,
)


def test_column_schema_diff_flags_missing_and_extra():
    diff = column_schema_diff([" time ", "icao24", "lat", "lon", "velocity", "heading",
                               "vertrate", "onground", "baroaltitude", "geoaltitude",
                               "lastcontact", "spare"])
    assert diff["matches_contract"] is True
    assert diff["extra"] == ["spare"]
    partial = column_schema_diff(["time", "icao24", "lat"])
    assert partial["matches_contract"] is False
    assert "lastcontact" in partial["missing_required"]


def test_dt_quantiles_on_one_second_track():
    times = np.arange(0, 100, 1.0)
    q = dt_quantiles(times)
    assert q["n_steps"] == 99
    assert q["p50"] == 1.0
    assert dt_quantiles([5.0])["n_steps"] == 0


def test_cadence_shares_mix_of_1s_10s_and_gaps():
    dt = np.array([1.0, 1.0, 10.0, 40.0])
    shares = cadence_shares(dt, gap_seconds=30.0)
    assert shares["share_dt_eq_1s"] == 0.5
    assert shares["share_dt_eq_10s"] == 0.25
    assert shares["share_dt_gt_gap"] == 0.25


def test_aircraft_recurrence_detects_cross_bucket_aircraft():
    buckets = {"h0": ["a", "b"], "h1": ["b", "c"], "h2": ["c"]}
    rec = aircraft_recurrence(buckets)
    assert rec["unique_aircraft"] == 3
    assert rec["aircraft_in_multiple_buckets"] == 2  # b and c
    assert rec["max_buckets_for_one_aircraft"] == 2


def test_cell_coverage_box_and_cells():
    cov = cell_coverage([0.0, 0.1, 10.0], [0.0, 0.1, 10.0], degrees=5.0)
    assert cov["n_points"] == 3
    assert cov["lat_min"] == 0.0 and cov["lat_max"] == 10.0
    assert cov["n_cells"] == 2  # (0,0.1) share a cell; 10.0 is another


def test_resample_count_estimate_rules():
    times = np.arange(0, 100, 1.0)  # 100 one-second rows
    decimate = resample_count_estimate(times, "decimate_mod10")
    assert decimate["estimated_rows"] == 10  # 0,10,...,90
    nearest = resample_count_estimate(times, "nearest_10s")
    assert nearest["estimated_rows"] == 10
    with pytest.raises(ValueError, match="unknown resampling rule"):
        resample_count_estimate(times, "bogus")


def _make_csv_tar(tmp_path, name="archive0.csv.tar"):
    csv = (
        "time,icao24,lat,lon,velocity,heading,vertrate,onground,baroaltitude,geoaltitude,lastcontact\n"
        "0,aaa,10.0,20.0,100.0,90.0,0.0,False,3000,3010,0\n"
        "1,aaa,10.1,20.1,100.0,90.0,0.0,False,3000,3010,1\n"
        "2,bbb,30.0,40.0,200.0,180.0,0.0,False,5000,5010,2\n"
    )
    path = tmp_path / name
    data = csv.encode("utf-8")
    with tarfile.open(path, "w") as tar:
        info = tarfile.TarInfo(name="archive0.csv")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return path


def test_audit_script_summary_end_to_end(tmp_path):
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "audit_hdd_source", root / "scripts" / "audit_hdd_source.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    archive = _make_csv_tar(tmp_path)
    summary = module.audit_archive(archive)
    assert summary["schema"]["matches_contract"] is True
    assert summary["rows"] == 3
    assert summary["n_unique_aircraft"] == 2
    assert set(EXPECTED_COLUMNS).issubset(summary["schema"]["observed"])
    # aaa has a 1 s cadence; the cadence summary should see one-second steps.
    assert summary["cadence"]["share_dt_eq_1s"] is not None
