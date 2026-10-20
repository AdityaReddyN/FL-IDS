import pandas as pd
import pytest

from flids.attacks.keys import (
    KEY_COLUMNS,
    NaturalKeyError,
    add_natural_keys,
    assert_natural_key_unique,
)


def sample_table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "icao24": ["b", "a", "a", "b"],
            "segment_id": [1, 2, 2, 1],
            "time": [20, 30, 10, 10],
            "value": [0, 1, 2, 3],
        }
    )


def test_segment_row_offset_is_time_order_within_segment() -> None:
    out = add_natural_keys(sample_table())
    offsets = out.set_index("source_row_id")["segment_row_offset"].to_dict()
    # (a, 2): row 2 at t=10 -> 0, row 1 at t=30 -> 1
    # (b, 1): row 3 at t=10 -> 0, row 0 at t=20 -> 1
    assert offsets == {0: 1, 1: 1, 2: 0, 3: 0}


def test_source_row_id_is_position_at_read_time() -> None:
    out = add_natural_keys(sample_table())
    assert out["source_row_id"].tolist() == [0, 1, 2, 3]


def test_add_natural_keys_does_not_mutate_input() -> None:
    original = sample_table()
    add_natural_keys(original)
    assert "source_row_id" not in original.columns
    assert "segment_row_offset" not in original.columns


def test_natural_key_is_unique() -> None:
    out = add_natural_keys(sample_table())
    assert_natural_key_unique(out)
    assert set(KEY_COLUMNS).issubset(out.columns)


def test_duplicate_source_key_raises_and_reports_count() -> None:
    df = sample_table()
    df.loc[4] = ["a", 2, 10, 4]  # duplicate of (a, 2, 10)
    with pytest.raises(NaturalKeyError, match="1 duplicate"):
        add_natural_keys(df)


def test_assert_natural_key_unique_reports_duplicates() -> None:
    df = add_natural_keys(sample_table())
    df.loc[0, "segment_row_offset"] = df.loc[2, "segment_row_offset"]
    # Force a duplicate natural key on the same segment.
    df.loc[0, "icao24"] = "a"
    df.loc[0, "segment_id"] = 2
    df.loc[0, "time"] = 10
    df.loc[0, "segment_row_offset"] = 0
    with pytest.raises(NaturalKeyError, match="1 duplicate"):
        assert_natural_key_unique(df)


def test_same_time_in_different_segments_is_allowed() -> None:
    df = pd.DataFrame(
        {"icao24": ["a", "a"], "segment_id": [1, 2], "time": [10, 10]}
    )
    out = add_natural_keys(df)
    assert out["segment_row_offset"].tolist() == [0, 0]
    assert_natural_key_unique(out)


def test_missing_required_columns_raise() -> None:
    with pytest.raises(NaturalKeyError, match="segment_id"):
        add_natural_keys(pd.DataFrame({"icao24": ["a"], "time": [1]}))


def test_null_icao24_raises() -> None:
    df = pd.DataFrame(
        {"icao24": [None, "a"], "segment_id": [1, 1], "time": [1, 2]}
    )
    with pytest.raises(NaturalKeyError, match="icao24"):
        add_natural_keys(df)


def test_null_segment_id_raises() -> None:
    df = pd.DataFrame(
        {"icao24": ["a", "a"], "segment_id": [None, 1], "time": [1, 2]}
    )
    with pytest.raises(NaturalKeyError, match="segment_id"):
        add_natural_keys(df)
