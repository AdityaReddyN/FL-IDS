"""Synthetic contract tests for the pure v3 overlay assembler."""

import json

import numpy as np
import pandas as pd

from flids.attacks.assembler import OverlaySpec, assemble_overlay, strict_json
from flids.attacks.schemas import TABLE_NAMES, validate_table
from flids.attacks.windows import label_windows

def _as_missing_none(series: pd.Series) -> pd.Series:
    """Compare nullable (<NA>) and float (nan) missing values as equal."""
    return series.astype(object).where(series.notna(), None)


def frame() -> pd.DataFrame:
    rows = []
    aircraft = (("a00001", "train"), ("a00002", "val"), ("a00003", "test"))
    for aircraft_index, (icao24, _split) in enumerate(aircraft):
        for segment_id, n_rows in ((0, 100), (1, 12)):
            for offset in range(n_rows):
                row = {
                    "icao24": icao24, "segment_id": segment_id,
                    "time": offset * 10, "lat": 30.0 + aircraft_index + offset * .001,
                    "lon": 10.0 + aircraft_index + offset * .001,
                    "velocity": 200.0, "heading": 90.0, "vertrate": 1.0,
                    "baroaltitude": 3000.0 + offset, "geoaltitude": 3010.0 + offset,
                    "onground": False, "contact_lag_seconds": 0.0,
                    "contact_lag_missing": False,
                }
                for name in ("lat", "lon", "velocity", "heading", "vertrate", "baroaltitude", "geoaltitude"):
                    row[f"{name}_missing"] = False
                rows.append(row)
    out = pd.DataFrame(rows)
    # Missing flags and values mirror the cleaned table; the short test segment
    # also exercises an all-missing position median.
    missing = (out.icao24 == "a00002") & (out.segment_id == 0) & (out.time == 500)
    out.loc[missing, ["lat", "lon"]] = np.nan
    out.loc[missing, ["lat_missing", "lon_missing"]] = True
    all_missing = (out.icao24 == "a00003") & (out.segment_id == 1)
    out.loc[all_missing, ["lat", "lon"]] = np.nan
    out.loc[all_missing, ["lat_missing", "lon_missing"]] = True
    lag_missing = (out.icao24 == "a00001") & (out.segment_id == 1) & (out.time == 0)
    out.loc[lag_missing, "contact_lag_seconds"] = np.nan
    out.loc[lag_missing, "contact_lag_missing"] = True
    return out


def split_of(icao24: str) -> str:
    return {"a00001": "train", "a00002": "val", "a00003": "test"}[icao24]


def overlay(**overrides) -> OverlaySpec:
    values = dict(
        attack_family="constant_deviation", tier="moderate", subtype="constant",
        duration_seconds=100, magnitude_m=5000.0, tau=1.0,
        episodes_per_segment=1,
    )
    values.update(overrides)
    return OverlaySpec(**values)


def assert_tables_valid(result) -> None:
    for name in TABLE_NAMES:
        validate_table(getattr(result, name), name)


def without_input_order_ids(table: pd.DataFrame) -> pd.DataFrame:
    ignored = ("row_id", "source_row_id", "start_source_row_id", "end_source_row_id", "replay_source_row_id")
    return table.drop(columns=[name for name in ignored if name in table])


def test_assembler_is_deterministic_order_independent_and_valid() -> None:
    source = frame()
    first = assemble_overlay(source, overlay(), 7, split_of)
    second = assemble_overlay(source.sample(frac=1.0, random_state=3), overlay(), 7, split_of)
    assert_tables_valid(first)
    assert_tables_valid(second)
    for name in TABLE_NAMES:
        left = without_input_order_ids(getattr(first, name))
        right = without_input_order_ids(getattr(second, name))
        left = left.sort_values(list(left.columns)).reset_index(drop=True)
        right = right.sort_values(list(right.columns)).reset_index(drop=True)
        pd.testing.assert_frame_equal(left, right)


def test_tau_selection_metadata_and_unmodified_rows_are_preserved() -> None:
    source = frame()
    none = assemble_overlay(source, overlay(tau=0.0), 7, split_of)
    assert not none.segments["selected"].any()
    assert not none.attacked_rows["is_attack_row"].any()
    all_eligible = assemble_overlay(source, overlay(tau=1.0), 7, split_of)
    assert all_eligible.segments.loc[all_eligible.segments.eligible, "selected"].all()
    rows = all_eligible.attacked_rows
    inactive = ~rows.is_attack_row
    for name in ("icao24", "segment_id", "time", "onground", "contact_lag_seconds", "contact_lag_missing"):
        pd.testing.assert_series_equal(
            _as_missing_none(rows.loc[inactive, name].reset_index(drop=True)),
            _as_missing_none(source.loc[rows.loc[inactive, "source_row_id"], name].reset_index(drop=True)),
            check_names=False,
            check_dtype=False,
        )
    assert np.array_equal(rows.loc[inactive, "orig_lat"], rows.loc[inactive, "mod_lat"], equal_nan=True)
    seed_a = assemble_overlay(source, overlay(tau=.5), 1, split_of)
    seed_b = assemble_overlay(source, overlay(tau=.5), 2, split_of)
    assert not seed_a.segments.selected.equals(seed_b.segments.selected)
    for segment in all_eligible.segments.itertuples():
        if segment.selected:
            accepted = len(all_eligible.episodes[(all_eligible.episodes.icao24 == segment.icao24) & (all_eligible.episodes.segment_id == segment.segment_id)])
            refused = len(all_eligible.rejected_candidates[(all_eligible.rejected_candidates.icao24 == segment.icao24) & (all_eligible.rejected_candidates.segment_id == segment.segment_id)])
            assert accepted + refused == 1
    assert "ineligible_interval" not in set(all_eligible.rejected_candidates.reason)


def test_provenance_windows_and_other_segment_isolation() -> None:
    source = frame()
    first = assemble_overlay(source, overlay(), 19, split_of)
    changed = source.copy()
    changed.loc[(changed.icao24 == "a00001") & (changed.segment_id == 0), "lat"] += .5
    second = assemble_overlay(changed, overlay(), 19, split_of)
    key = (first.attacked_rows.icao24 != "a00001")
    pd.testing.assert_frame_equal(
        first.attacked_rows.loc[key].reset_index(drop=True),
        second.attacked_rows.loc[key].reset_index(drop=True),
    )
    assert set(first.modified_row_provenance.source_row_id) <= set(first.attacked_rows.loc[first.attacked_rows.is_attack_row, "source_row_id"])
    assert first.modified_row_provenance.changed_fields_json.str.len().gt(2).all()
    for (_, _), group in first.attacked_rows.groupby(["icao24", "segment_id"]):
        expected = label_windows(group.ramp_multiplier, group.episode_position, group.episode_id.fillna(-1))
        actual = first.windows[(first.windows.icao24 == group.iloc[0].icao24) & (first.windows.segment_id == group.iloc[0].segment_id)]
        assert actual[["label", "stratum", "n_attack_rows", "n_effective_rows"]].to_dict("records") == [{k: item[k] for k in ("label", "stratum", "n_attack_rows", "n_effective_rows")} for item in expected]


def test_replay_and_baro_plus_geo_glitch_screen() -> None:
    source = frame()
    replay = assemble_overlay(source, overlay(attack_family="replay_partial_field", subtype="replay", duration_seconds=100, replay_delay_s=300.0), 9, split_of)
    active = replay.attacked_rows[replay.attacked_rows.is_attack_row]
    assert not active.empty
    assert active.replay_source_row_id.notna().all()
    for row in active.itertuples():
        source_row = replay.attacked_rows[replay.attacked_rows.source_row_id == row.replay_source_row_id].iloc[0]
        assert (source_row.icao24, source_row.segment_id) == (row.icao24, row.segment_id)
        assert abs(source_row.time - (row.time - 300.0)) <= 5.0
    source.loc[(source.icao24 == "a00001") & (source.segment_id == 0) & (source.time == 400), "geoaltitude"] += 9999
    altitude = assemble_overlay(source, overlay(attack_family="altitude_constant_deviation", subtype="altitude", altitude_variant="baro_plus_geo", shift_m=125.0, geoaltitude_glitch_threshold_m=1000.0), 3, split_of)
    row = altitude.attacked_rows[(altitude.attacked_rows.icao24 == "a00001") & (altitude.attacked_rows.segment_id == 0) & (altitude.attacked_rows.time == 400)]
    assert not row.is_attack_row.any()


def test_episode_and_rejection_ids_are_unique_for_three_requests() -> None:
    tables = assemble_overlay(frame(), overlay(episodes_per_segment=3), 3, split_of)
    values = list(tables.episodes.episode_id) + list(tables.rejected_candidates.candidate_id)
    assert len(values) == len(set(values))


def test_strict_json_converts_non_finite_values_to_null() -> None:
    assert strict_json({"x": np.nan, "y": np.inf}) == '{"x":null,"y":null}'


def test_missing_feature_rows_pass_through_and_provenance_stays_finite() -> None:
    tables = assemble_overlay(frame(), overlay(), 7, split_of)
    missing = tables.attacked_rows[tables.attacked_rows.orig_lat.isna()]
    assert not missing.empty
    assert missing.mod_lat.isna().all()
    assert not missing.is_attack_row.any()
    for row in tables.modified_row_provenance.itertuples():
        original = json.loads(row.orig_values_json)
        modified = json.loads(row.mod_values_json)
        assert np.isfinite(np.asarray(list(original.values()), dtype=float)).all()
        assert np.isfinite(np.asarray(list(modified.values()), dtype=float)).all()
        assert "NaN" not in row.orig_values_json + row.mod_values_json


def test_all_missing_position_segment_has_unknown_cell_without_warning() -> None:
    tables = assemble_overlay(frame(), overlay(), 7, split_of)
    segment = tables.segments[(tables.segments.icao24 == "a00003") & (tables.segments.segment_id == 1)]
    assert segment.cell_id.iloc[0] == "unknown"


def test_same_seed_uses_independent_selection_for_overlay_keys() -> None:
    source = frame()
    constant = assemble_overlay(source, overlay(tau=.5), 42, split_of)
    gaussian = assemble_overlay(
        source,
        overlay(attack_family="random_gaussian_deviation", subtype="gaussian", magnitude_m=None, sigma_m=500.0, tau=.5),
        42,
        split_of,
    )
    assert not constant.segments.selection_u.equals(gaussian.segments.selection_u)


def test_missing_contact_lag_is_preserved_with_its_missing_flag() -> None:
    tables = assemble_overlay(frame(), overlay(), 7, split_of)
    row = tables.attacked_rows[(tables.attacked_rows.icao24 == "a00001") & (tables.attacked_rows.segment_id == 1) & (tables.attacked_rows.time == 0)].iloc[0]
    assert pd.isna(row.contact_lag_seconds)
    assert row.contact_lag_missing
