from __future__ import annotations

import numpy as np
import pandas as pd
import json
import pytest

from flids.data.sequences_v3 import build_sequence_arrays, save_sequence_dataset


def fixture_tables():
    rows = []
    windows = []
    source_id = 0
    for aircraft, split in (("a1", "train"), ("a2", "val"), ("a3", "test")):
        for segment_id in (1, 2):
            n = 40
            for offset in range(n):
                attack = split == "train" and segment_id == 2 and 10 <= offset < 20
                rows.append({
                    "source_row_id": source_id, "icao24": aircraft,
                    "segment_id": segment_id, "time": offset * 10,
                    "segment_row_offset": offset, "split": split,
                    "mod_lat": 10.0 + offset, "mod_lon": 20.0 + offset,
                    "mod_velocity": 200.0, "mod_heading": 90.0,
                    "mod_vertrate": 0.0, "mod_baroaltitude": 1000.0,
                    "mod_geoaltitude": 1100.0, "onground": False,
                    "contact_lag_seconds": 0.0, "contact_lag_missing": False,
                    "is_attack_row": attack, "attack_family": "constant_deviation" if attack else None,
                    "episode_id": 7 if attack else None, "episode_position": "interior" if attack else "none",
                })
                source_id += 1
            # One full 30-row window per segment.
            attacked = split == "train" and segment_id == 2
            windows.append({
                "window_id": len(windows), "icao24": aircraft,
                "segment_id": segment_id, "split": split,
                "start_offset": 0, "n_rows": 30,
                "label": "attacked" if attacked else "normal",
                "stratum": "interior_only" if attacked else "none",
                "n_attack_rows": 10 if attacked else 0,
                "n_effective_rows": 10 if attacked else 0,
                "episode_id": 7 if attacked else -1,
                "attack_family": "constant_deviation" if attacked else None,
                "attack_subtype": None, "tier": "subtle" if attacked else None,
            })
    return pd.DataFrame(rows), pd.DataFrame(windows)


def test_builder_emits_finite_train_scaled_windows_and_split_metadata():
    rows, windows = fixture_tables()
    built = build_sequence_arrays(rows, windows, seed=5)
    assert built["X_train"].shape == (2, 30, 15)
    assert built["X_val"].shape == (2, 30, 15)
    assert built["X_test"].shape == (2, 30, 15)
    assert np.isfinite(built["X_train"]).all()
    assert built["y_binary_train"].tolist() == [0, 1]
    assert built["y_multiclass_train"].tolist() == [0, 1]
    assert built["metadata_train"].icao24.tolist() == ["a1", "a1"]
    assert built["metadata_val"].icao24.tolist() == ["a2", "a2"]


def test_balanced_train_indices_are_seeded_and_keep_binary_classes_equal():
    rows, windows = fixture_tables()
    built_a = build_sequence_arrays(rows, windows, seed=7)
    built_b = build_sequence_arrays(rows, windows, seed=7)
    assert np.array_equal(built_a["balanced_train_indices"], built_b["balanced_train_indices"])
    labels = built_a["y_binary_train"][built_a["balanced_train_indices"]]
    assert np.bincount(labels, minlength=2).tolist() == [1, 1]


def test_builder_rejects_aircraft_that_cross_splits():
    rows, windows = fixture_tables()
    rows.loc[rows.icao24 == "a1", "split"] = "val"
    with pytest.raises(ValueError, match="split"):
        build_sequence_arrays(rows, windows, seed=0)


def test_missing_values_use_explicit_masks_and_train_only_scaler():
    rows, windows = fixture_tables()
    rows.loc[(rows.icao24 == "a1") & (rows.segment_id == 1) & (rows.segment_row_offset == 0), "mod_lat"] = np.nan
    built = build_sequence_arrays(rows, windows, seed=5)
    assert np.isfinite(built["X_train"]).all()
    assert built["X_train"][0, 0, 8] == 1.0
    train_window_rows = rows.loc[(rows.split == "train") & (rows.segment_row_offset < 30), "mod_lat"]
    assert built["scaler_mean"][0] == pytest.approx(np.nanmean(train_window_rows))


def test_input_row_order_does_not_change_built_arrays():
    rows, windows = fixture_tables()
    expected = build_sequence_arrays(rows, windows, seed=19)
    shuffled = build_sequence_arrays(
        rows.sample(frac=1, random_state=2).reset_index(drop=True),
        windows.sample(frac=1, random_state=3).reset_index(drop=True),
        seed=19,
    )
    for split in ("train", "val", "test"):
        np.testing.assert_array_equal(expected[f"X_{split}"], shuffled[f"X_{split}"])
        np.testing.assert_array_equal(expected[f"y_binary_{split}"], shuffled[f"y_binary_{split}"])
        pd.testing.assert_frame_equal(expected[f"metadata_{split}"], shuffled[f"metadata_{split}"])


def test_balanced_train_and_conditioned_val_match_missingness_counts():
    rows, windows = fixture_tables()
    built = build_sequence_arrays(rows, windows, seed=19)
    train_idx = built["balanced_train_indices"]
    train_y = built["y_binary_train"][train_idx]
    train_missing = built["X_train"][:, :, 8:].sum(axis=(1, 2))[train_idx]
    assert np.array_equal(
        np.sort(train_missing[train_y == 0]),
        np.sort(train_missing[train_y == 1]),
    )
    val_idx = built["missingness_matched_val_indices"]
    val_y = built["y_binary_val"][val_idx]
    val_missing = built["X_val"][:, :, 8:].sum(axis=(1, 2))[val_idx]
    assert np.array_equal(
        np.sort(val_missing[val_y == 0]),
        np.sort(val_missing[val_y == 1]),
    )


def test_save_sequence_dataset_writes_manifest_hashes_and_refuses_overwrite(tmp_path):
    rows, windows = fixture_tables()
    built = build_sequence_arrays(rows, windows, seed=19)
    out = tmp_path / "dataset"
    manifest = save_sequence_dataset(built, out, config={"seed": 19})
    assert manifest["dataset_version"] == "sequences_v3"
    assert "X_train.npy" in manifest["table_sha256"]
    assert json.loads((out / "manifest.json").read_text())["counts"]["metadata_val"] == 2
    with pytest.raises(FileExistsError):
        save_sequence_dataset(built, out, config={"seed": 19})
