"""Synthetic contract tests for the pure v3 overlay assembler."""

import numpy as np
import pandas as pd

from flids.attacks.assembler import OverlaySpec, assemble_overlay
from flids.attacks.schemas import TABLE_NAMES, validate_table
from flids.attacks.windows import label_windows


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
    # One ineligible row excludes the long segment's affected candidate spans.
    out.loc[(out.icao24 == "a00002") & (out.segment_id == 0) & (out.time == 500), "lat_missing"] = True
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


def test_assembler_is_deterministic_order_independent_and_valid() -> None:
    source = frame()
    first = assemble_overlay(source, overlay(), 7, split_of)
    second = assemble_overlay(source.copy(), overlay(), 7, split_of)
    assert_tables_valid(first)
    assert_tables_valid(second)
    for name in TABLE_NAMES:
        left = getattr(first, name).sort_values(list(getattr(first, name).columns)).reset_index(drop=True)
        right = getattr(second, name).sort_values(list(getattr(second, name).columns)).reset_index(drop=True)
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
        assert rows.loc[inactive, name].tolist() == source.loc[rows.loc[inactive, "source_row_id"], name].tolist()
    assert (rows.loc[inactive, "orig_lat"] == rows.loc[inactive, "mod_lat"]).all()
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
    assert (active.replay_source_row_id < active.source_row_id).all()
    source.loc[(source.icao24 == "a00001") & (source.segment_id == 0) & (source.time == 400), "geoaltitude"] += 9999
    altitude = assemble_overlay(source, overlay(attack_family="altitude_constant_deviation", subtype="altitude", altitude_variant="baro_plus_geo", shift_m=125.0, geoaltitude_glitch_threshold_m=1000.0), 3, split_of)
    row = altitude.attacked_rows[(altitude.attacked_rows.icao24 == "a00001") & (altitude.attacked_rows.segment_id == 0) & (altitude.attacked_rows.time == 400)]
    assert not row.is_attack_row.any()
