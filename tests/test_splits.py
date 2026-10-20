import json

import pytest

from flids.attacks.splits import (
    SplitError,
    load_split_aircraft,
    validate_splits,
)


def write_split(tmp_path, data: dict):
    path = tmp_path / "split_aircraft.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_split_and_lookup(tmp_path) -> None:
    path = write_split(
        tmp_path,
        {"train": ["a", "b"], "val": ["c"], "test": ["d"]},
    )
    splits = load_split_aircraft(path)
    assert splits.split_of("a") == "train"
    assert splits.split_of("d") == "test"
    assert splits.counts == {"train": 2, "val": 1, "test": 1}
    assert splits.aircraft == frozenset({"a", "b", "c", "d"})


def test_unknown_aircraft_raises_key_error(tmp_path) -> None:
    splits = load_split_aircraft(
        write_split(tmp_path, {"train": ["a"], "val": [], "test": []})
    )
    with pytest.raises(KeyError):
        splits.split_of("missing")


def test_overlapping_splits_raise(tmp_path) -> None:
    path = write_split(
        tmp_path,
        {"train": ["a", "b"], "val": ["b"], "test": []},
    )
    with pytest.raises(SplitError, match="overlap"):
        load_split_aircraft(path)


def test_duplicate_within_split_raises(tmp_path) -> None:
    path = write_split(tmp_path, {"train": ["a", "a"], "val": [], "test": []})
    with pytest.raises(SplitError, match="duplicate"):
        load_split_aircraft(path)


def test_missing_split_name_raises(tmp_path) -> None:
    path = write_split(tmp_path, {"train": ["a"], "val": []})
    with pytest.raises(SplitError, match="test"):
        load_split_aircraft(path)


def test_unexpected_split_name_raises(tmp_path) -> None:
    path = write_split(
        tmp_path, {"train": ["a"], "val": [], "test": [], "holdout": []}
    )
    with pytest.raises(SplitError, match="unexpected"):
        load_split_aircraft(path)


def test_validate_coverage_exact(tmp_path) -> None:
    splits = load_split_aircraft(
        write_split(tmp_path, {"train": ["a"], "val": ["b"], "test": ["c"]})
    )
    validate_splits(splits, expected_icao24=["a", "b", "c"])


def test_validate_coverage_reports_missing_and_extraneous(tmp_path) -> None:
    splits = load_split_aircraft(
        write_split(tmp_path, {"train": ["a"], "val": ["b"], "test": ["c"]})
    )
    with pytest.raises(SplitError, match="missing"):
        validate_splits(splits, expected_icao24=["a", "b", "c", "d"])
    with pytest.raises(SplitError, match="extraneous"):
        validate_splits(splits, expected_icao24=["a", "b"])
