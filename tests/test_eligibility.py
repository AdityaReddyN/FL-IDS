import numpy as np
import pandas as pd
import pytest

from flids.attacks.eligibility import (
    REQUIRED_FIELDS,
    eligible_starts,
    pair_valid,
    replay_source_offsets,
    row_eligible,
)

FEATURES = (
    "lat",
    "lon",
    "velocity",
    "heading",
    "vertrate",
    "baroaltitude",
    "geoaltitude",
)


def make_segment(n: int = 6) -> pd.DataFrame:
    defaults = {
        "lat": 10.0,
        "lon": 20.0,
        "velocity": 100.0,
        "heading": 90.0,
        "vertrate": 0.0,
        "baroaltitude": 3000.0,
        "geoaltitude": 3000.0,
    }
    data = {
        "icao24": ["abc"] * n,
        "segment_id": [1] * n,
        "time": np.arange(n, dtype=np.int64) * 10 + 1000,
        "onground": [False] * n,
        "contact_lag_seconds": [1.0] * n,
        "contact_lag_missing": [False] * n,
    }
    data.update({field: [value] * n for field, value in defaults.items()})
    data.update({f"{field}_missing": [0] * n for field in FEATURES})
    return pd.DataFrame(data)


def test_row_eligible_all_good() -> None:
    df = make_segment()
    mask = row_eligible(df, REQUIRED_FIELDS["horizontal_manipulation"])
    assert mask.dtype == bool
    assert mask.all()


def test_row_eligible_rejects_onground() -> None:
    df = make_segment()
    df.loc[2, "onground"] = True
    mask = row_eligible(df, REQUIRED_FIELDS["horizontal_manipulation"])
    assert not mask[2]
    assert mask.sum() == len(df) - 1


def test_row_eligible_contact_lag_bounds_and_missing_flag() -> None:
    df = make_segment()
    df.loc[1, "contact_lag_seconds"] = 30.0
    df.loc[2, "contact_lag_seconds"] = 31.0
    df.loc[3, "contact_lag_seconds"] = np.nan
    df.loc[4, "contact_lag_missing"] = True
    mask = row_eligible(df, REQUIRED_FIELDS["horizontal_manipulation"])
    assert mask.tolist() == [True, True, False, False, False, True]


def test_row_eligible_rejects_null_field_and_flag() -> None:
    df = make_segment()
    df.loc[1, "lat"] = np.nan
    df.loc[2, "lon_missing"] = 1
    mask = row_eligible(df, REQUIRED_FIELDS["horizontal_manipulation"])
    assert mask.tolist() == [True, False, False, True, True, True]


def test_missing_velocity_makes_lat_lon_manipulation_ineligible() -> None:
    df = make_segment()
    df.loc[2, "velocity"] = np.nan
    mask = row_eligible(df, REQUIRED_FIELDS["horizontal_manipulation"])
    assert not mask[2]


def test_required_fields_include_effect_measurement_fields() -> None:
    assert set(REQUIRED_FIELDS["horizontal_manipulation"]) == {
        "lat",
        "lon",
        "velocity",
        "heading",
    }
    assert set(REQUIRED_FIELDS["freeze"]) == {"lat", "lon", "velocity", "heading"}
    assert set(REQUIRED_FIELDS["altitude_manipulation"]) == {
        "baroaltitude",
        "vertrate",
    }
    assert "geoaltitude" in REQUIRED_FIELDS["altitude_manipulation_baro_plus_geo"]
    assert set(REQUIRED_FIELDS["replay_full_field"]) == set(FEATURES)


def test_pair_valid_time_and_segment_rules() -> None:
    df = make_segment(5)
    assert pair_valid(df).tolist() == [False, True, True, True, True]

    same_time = make_segment(3)
    same_time.loc[1, "time"] = same_time.loc[0, "time"]
    assert pair_valid(same_time).tolist() == [False, False, True]

    long_gap = make_segment(3)
    long_gap.loc[2, "time"] = long_gap.loc[1, "time"] + 31
    assert pair_valid(long_gap).tolist() == [False, True, False]

    new_segment = make_segment(3)
    new_segment.loc[2, "segment_id"] = 2
    assert pair_valid(new_segment).tolist() == [False, True, False]

    new_aircraft = make_segment(3)
    new_aircraft.loc[2, "icao24"] = "def"
    assert pair_valid(new_aircraft).tolist() == [False, True, False]


def test_pair_valid_requires_rows_sorted_by_key() -> None:
    shuffled = make_segment(4).iloc[[0, 2, 1, 3]].reset_index(drop=True)
    with pytest.raises(ValueError, match="sorted by"):
        pair_valid(shuffled)

    aircraft = make_segment(3)
    aircraft.loc[:, "icao24"] = ["a", "b", "a"]
    with pytest.raises(ValueError, match="sorted by"):
        pair_valid(aircraft)

    segment = make_segment(3)
    segment.loc[:, "segment_id"] = [1, 2, 1]
    with pytest.raises(ValueError, match="sorted by"):
        pair_valid(segment)


def test_pair_valid_rejects_null_keys() -> None:
    frame = make_segment(3)
    frame["time"] = frame["time"].astype(float)
    frame.loc[1, "time"] = np.nan
    with pytest.raises(ValueError, match="non-null"):
        pair_valid(frame)


def test_eligible_starts_all_good() -> None:
    df = make_segment(6)
    row_ok = row_eligible(df, REQUIRED_FIELDS["horizontal_manipulation"])
    pair_ok = pair_valid(df)
    assert eligible_starts(df, 3, row_ok, pair_ok).tolist() == [0, 1, 2, 3]


def test_eligible_starts_row_and_pair_filters() -> None:
    df = make_segment(6)
    row_ok = row_eligible(df, REQUIRED_FIELDS["horizontal_manipulation"])
    pair_ok = pair_valid(df)
    row_ok[2] = False
    assert eligible_starts(df, 3, row_ok, pair_ok).tolist() == [3]

    pair_ok[2] = False
    assert eligible_starts(df, 3, row_ok, pair_ok).tolist() == [3]

    row_ok[:] = True
    assert eligible_starts(df, 3, row_ok, pair_ok).tolist() == [2, 3]
    assert eligible_starts(df, 7, row_ok, pair_ok).tolist() == []


def test_eligible_starts_rejects_multiple_segments() -> None:
    df = make_segment(4)
    df.loc[3, "segment_id"] = 2
    row_ok = np.ones(4, dtype=bool)
    pair_ok = np.ones(4, dtype=bool)
    with pytest.raises(ValueError, match="single segment"):
        eligible_starts(df, 2, row_ok, pair_ok)


def test_replay_source_offsets_nearest_and_bounds() -> None:
    times = np.arange(0, 610, 10, dtype=np.int64)
    eligible = np.ones(len(times), dtype=bool)
    sources = replay_source_offsets(times, eligible, delay_s=300, tolerance_s=5)
    assert sources[30] == 0
    assert sources[31] == 1
    assert sources[0] == -1
    assert sources[29] == -1

    far = replay_source_offsets(
        np.array([0, 100], dtype=np.int64),
        np.ones(2, dtype=bool),
        delay_s=300,
        tolerance_s=5,
    )
    assert far.tolist() == [-1, -1]


def test_replay_source_offsets_ties_go_to_earlier() -> None:
    times = np.array([0, 10, 305], dtype=np.int64)
    sources = replay_source_offsets(
        times, np.ones(3, dtype=bool), delay_s=300, tolerance_s=20
    )
    assert sources[2] == 0


def test_replay_source_must_be_eligible_without_fallback() -> None:
    times = np.array([0, 10, 310], dtype=np.int64)
    eligible = np.array([False, True, True])
    sources = replay_source_offsets(
        times, eligible, delay_s=300, tolerance_s=20
    )
    # Desired time is 10; row 1 is exactly 10 but row 0 is ineligible
    assert sources[2] == 1

    times = np.array([0, 10, 305], dtype=np.int64)
    eligible = np.array([False, True, True])
    sources = replay_source_offsets(
        times, eligible, delay_s=300, tolerance_s=20
    )
    # Nearest row is 0 (ineligible); no fallback to row 1.
    assert sources[2] == -1


def test_replay_source_does_not_depend_on_target_eligibility() -> None:
    times = np.array([0, 10, 310], dtype=np.int64)
    eligible = np.array([True, True, False])
    sources = replay_source_offsets(times, eligible, delay_s=300, tolerance_s=5)
    assert sources[2] == 1


def test_replay_source_requires_sorted_times() -> None:
    with pytest.raises(ValueError, match="sorted"):
        replay_source_offsets(
            np.array([0, 10, 5], dtype=np.int64), np.ones(3, dtype=bool)
        )
