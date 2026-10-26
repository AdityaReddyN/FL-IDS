"""Tests for ranked quota selection (S2)."""

import numpy as np
import pandas as pd
import pytest

from flids.attacks.assembler import OverlaySpec, assemble_overlay
from flids.attacks.quota import (
    CapacityShortfallError,
    QuotaTarget,
    overlay_capacity,
    select_quota_segments,
)

FEATURES = ("lat", "lon", "velocity", "heading", "vertrate", "baroaltitude", "geoaltitude")


def frame(n_aircraft: int = 12, n_rows: int = 60) -> pd.DataFrame:
    rows = []
    for a in range(n_aircraft):
        icao = f"a{a:05d}"
        for offset in range(n_rows):
            row = {
                "icao24": icao, "segment_id": 0, "time": offset * 10,
                "lat": 30.0 + a + offset * 0.001, "lon": 10.0 + a + offset * 0.001,
                "velocity": 200.0, "heading": 90.0, "vertrate": 1.0,
                "baroaltitude": 3000.0 + offset, "geoaltitude": 3010.0 + offset,
                "onground": False, "contact_lag_seconds": 0.0, "contact_lag_missing": False,
                **{f"{name}_missing": False for name in FEATURES},
            }
            rows.append(row)
    return pd.DataFrame(rows)


def split_of(_icao24: str) -> str:
    return "train"


def overlay(**kw) -> OverlaySpec:
    values = dict(attack_family="constant_deviation", tier="moderate", subtype="constant",
                  duration_seconds=100, magnitude_m=5000.0, tau=0.5)
    values.update(kw)
    return OverlaySpec(**values)


def target(episodes: int, aircraft: int) -> QuotaTarget:
    return QuotaTarget(episodes={"train": episodes, "val": 0, "test": 0},
                       unique_aircraft={"train": aircraft, "val": 0, "test": 0})


def test_quota_selection_is_deterministic_and_order_independent():
    ov = overlay()
    targets = {ov.overlay_key: target(5, 0)}
    df = frame()
    first = select_quota_segments(df, [ov], 7, split_of, targets)["chosen"]
    second = select_quota_segments(df, [ov], 7, split_of, targets)["chosen"]
    shuffled = df.sample(frac=1.0, random_state=1).reset_index(drop=True)
    third = select_quota_segments(shuffled, [ov], 7, split_of, targets)["chosen"]
    assert first == second == third
    assert len(first) == 5


def test_quota_honors_unique_aircraft_target():
    ov = overlay()
    targets = {ov.overlay_key: target(1, 8)}  # one episode, but eight aircraft
    result = select_quota_segments(frame(), [ov], 7, split_of, targets)
    cell = [c for c in result["per_cell"] if c["split"] == "train"][0]
    assert cell["realized_unique_aircraft"] >= 8
    assert cell["realized_segments"] >= 8  # must keep picking to reach 8 aircraft


def test_quota_shortfall_raises_with_per_cell_table():
    ov = overlay()
    targets = {ov.overlay_key: target(999, 0)}  # more than the 12 eligible segments
    with pytest.raises(CapacityShortfallError) as info:
        select_quota_segments(frame(), [ov], 7, split_of, targets)
    table = info.value.shortfall_table
    assert table and table[0]["overlay_key"] == ov.overlay_key
    assert table[0]["episodes_shortfall"] is True


def test_quota_shortfall_reported_when_not_failing():
    ov = overlay()
    targets = {ov.overlay_key: target(999, 0)}
    result = select_quota_segments(frame(), [ov], 7, split_of, targets,
                                   fail_on_capacity_shortfall=False)
    assert result["shortfall"]
    assert len(result["chosen"]) == 12  # all eligible selected


def test_overlay_capacity_counts_eligible_segments_and_aircraft():
    ov = overlay()
    capacity = overlay_capacity(frame(n_aircraft=6), ov, 7, split_of)
    assert capacity["train"]["eligible_segments"] == 6
    assert capacity["train"]["unique_aircraft"] == 6
    assert capacity["train"]["eligible_starts"] > 0
    assert capacity["val"]["eligible_segments"] == 0


def test_ranked_selection_equals_bernoulli_when_not_binding():
    ov = overlay(tau=0.5)
    df = frame()
    tables = assemble_overlay(df, ov, 7, split_of)
    bernoulli = tables.overlay_selections[tables.overlay_selections.selected]
    bernoulli_set = {
        (str(r.icao24), int(r.segment_id), str(r.overlay_key))
        for r in bernoulli.itertuples()
    }
    # Quota target equal to the Bernoulli count selects exactly the same lowest-u segments.
    targets = {ov.overlay_key: target(len(bernoulli_set), 0)}
    chosen = select_quota_segments(df, [ov], 7, split_of, targets)["chosen"]
    assert chosen == bernoulli_set
