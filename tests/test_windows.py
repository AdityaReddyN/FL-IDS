"""Window labelling tests (D-024)."""

import numpy as np
import pytest

from flids.attacks.ramps import ramp_multipliers
from flids.attacks.windows import WINDOW_STRIDE, label_windows


def place_episodes(n_rows, episodes):
    """Return multipliers, positions, episode ids for (start, length) episodes."""
    multipliers = np.zeros(n_rows)
    positions = np.full(n_rows, "none", dtype=object)
    episode_ids = np.full(n_rows, -1, dtype=np.int64)
    for episode_id, (start, length) in enumerate(episodes):
        ramp, ramp_positions = ramp_multipliers(length, 3, "linear_mix")
        stop = start + length
        multipliers[start:stop] = ramp
        positions[start:stop] = ramp_positions
        episode_ids[start:stop] = episode_id
    return multipliers, positions, episode_ids


def reference_windows(multipliers, positions, episode_ids, window_rows, stride):
    """Brute-force reference mirroring build_sequences_v2 anchoring."""
    output = []
    window_id = 0
    for start in range(0, len(multipliers) - window_rows + 1, stride):
        stop = start + window_rows
        multipliers_window = multipliers[start:stop]
        positions_window = positions[start:stop]
        ids_window = episode_ids[start:stop]
        attack = multipliers_window > 0.0
        effective = multipliers_window >= 0.5
        n_attack = int(np.count_nonzero(attack))
        n_effective = int(np.count_nonzero(effective))
        if n_attack == 0:
            label = "normal"
            stratum = "none"
            episode_id = -1
        else:
            live_ids = set(int(value) for value in ids_window[attack])
            assert len(live_ids) == 1
            episode_id = live_ids.pop()
            if n_effective >= 5:
                label = "attacked"
            else:
                label = "ambiguous"
            boundary = any(
                positions_window[index] in ("onset", "offset")
                for index in np.flatnonzero(attack)
            )
            stratum = "boundary" if boundary else "interior_only"
        output.append(
            {
                "window_id": window_id,
                "start_offset": start,
                "n_rows": window_rows,
                "label": label,
                "stratum": stratum,
                "n_attack_rows": n_attack,
                "n_effective_rows": n_effective,
                "episode_id": episode_id,
            }
        )
        window_id += 1
    return output


def test_empty_episode_list_marks_every_window_normal() -> None:
    n_rows = 100
    windows = label_windows(
        np.zeros(n_rows), np.full(n_rows, "none", dtype=object),
        np.full(n_rows, -1, dtype=np.int64),
    )
    assert len(windows) == len(range(0, 100 - 30 + 1, WINDOW_STRIDE))
    for window in windows:
        assert window["label"] == "normal"
        assert window["stratum"] == "none"
        assert window["episode_id"] == -1
        assert window["n_attack_rows"] == 0
        assert window["n_effective_rows"] == 0


def test_starts_mirror_v2_full_window_anchoring() -> None:
    def starts(n_rows):
        multipliers, positions, ids = place_episodes(
            n_rows, [(10, 10)] if n_rows >= 20 else []
        )
        return [
            window["start_offset"]
            for window in label_windows(multipliers, positions, ids)
        ]

    assert starts(35) == [0]
    assert starts(39) == [0]
    assert starts(40) == [0, 10]
    assert starts(29) == []


def test_twelve_row_episode_never_yields_interior_only() -> None:
    multipliers, positions, ids = place_episodes(100, [(10, 12)])
    windows = label_windows(multipliers, positions, ids)
    labelled = [w for w in windows if w["label"] != "normal"]
    assert labelled
    assert all(w["stratum"] == "boundary" for w in labelled)
    assert all(w["episode_id"] == 0 for w in labelled)
    assert not [w for w in windows if w["stratum"] == "interior_only"]


def test_sixty_row_aligned_episode_has_two_interior_only_windows() -> None:
    multipliers, positions, ids = place_episodes(120, [(30, 60)])
    windows = label_windows(multipliers, positions, ids)
    interior = [w for w in windows if w["stratum"] == "interior_only"]
    assert [w["start_offset"] for w in interior] == [40, 50]
    assert all(w["label"] == "attacked" for w in interior)
    assert all(w["n_attack_rows"] == 30 for w in interior)


def test_nine_row_episode_has_seven_effective_rows() -> None:
    multipliers, positions, ids = place_episodes(120, [(20, 9)])
    windows = label_windows(multipliers, positions, ids)
    by_start = {w["start_offset"]: w for w in windows}
    assert by_start[20]["n_attack_rows"] == 9
    assert by_start[20]["n_effective_rows"] == 7
    assert by_start[20]["label"] == "attacked"


def test_weak_overlap_is_ambiguous() -> None:
    multipliers, positions, ids = place_episodes(120, [(27, 9)])
    windows = label_windows(multipliers, positions, ids)
    by_start = {w["start_offset"]: w for w in windows}
    assert by_start[0]["n_attack_rows"] == 3
    assert by_start[0]["n_effective_rows"] == 2
    assert by_start[0]["label"] == "ambiguous"
    assert by_start[0]["stratum"] == "boundary"
    assert by_start[10]["label"] == "attacked"


def test_random_episodes_match_brute_force_reference() -> None:
    rng = np.random.default_rng(2026)
    for _ in range(25):
        n_rows = int(rng.integers(260, 320))
        episodes = [
            (5, int(rng.integers(9, 46))),
            (80, int(rng.integers(9, 70))),
            (170, int(rng.integers(9, 61))),
        ]
        multipliers, positions, ids = place_episodes(n_rows, episodes)
        expected = reference_windows(multipliers, positions, ids, 30, 10)
        assert label_windows(multipliers, positions, ids) == expected


def test_multiple_episodes_in_one_window_raise() -> None:
    multipliers, positions, ids = place_episodes(120, [(10, 9), (20, 9)])
    with pytest.raises(AssertionError, match="overlaps"):
        label_windows(multipliers, positions, ids)


def test_window_over_episode_boundary_is_marked_boundary() -> None:
    multipliers, positions, ids = place_episodes(120, [(30, 60)])
    by_start = {w["start_offset"]: w for w in label_windows(multipliers, positions, ids)}
    assert by_start[30]["stratum"] == "boundary"
    assert by_start[60]["stratum"] == "boundary"
    assert by_start[0]["label"] == "normal"


def test_argument_validation() -> None:
    n_rows = 60
    multipliers = np.zeros(n_rows)
    positions = np.full(n_rows, "none", dtype=object)
    ids = np.full(n_rows, -1, dtype=np.int64)
    with pytest.raises(ValueError, match="equal length"):
        label_windows(multipliers, positions[:-1], ids)
    with pytest.raises(ValueError, match="window_rows"):
        label_windows(multipliers, positions, ids, window_rows=0)
    with pytest.raises(ValueError, match="stride"):
        label_windows(multipliers, positions, ids, stride=0)
    with pytest.raises(ValueError, match="multipliers"):
        label_windows(multipliers * np.nan, positions, ids)


def test_window_ids_are_sequential() -> None:
    multipliers, positions, ids = place_episodes(100, [(10, 12)])
    windows = label_windows(multipliers, positions, ids)
    assert [w["window_id"] for w in windows] == list(range(len(windows)))
