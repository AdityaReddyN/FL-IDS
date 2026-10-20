import numpy as np
import pytest

from flids.attacks.ramps import (
    ATTACK_THRESHOLD,
    EFFECTIVE_THRESHOLD,
    attack_row_mask,
    effective_row_mask,
    ramp_multipliers,
)


def test_linear_mix_multipliers_and_positions() -> None:
    a, positions = ramp_multipliers(9, ramp_rows=3, mode="linear_mix")
    assert a.dtype == np.float64
    assert a.tolist() == [0.25, 0.5, 0.75, 1.0, 1.0, 1.0, 0.75, 0.5, 0.25]
    assert positions.tolist() == [
        "onset",
        "onset",
        "onset",
        "interior",
        "interior",
        "interior",
        "offset",
        "offset",
        "offset",
    ]


def test_linear_mix_mirrors_onset_on_offset() -> None:
    a, positions = ramp_multipliers(7, ramp_rows=2, mode="linear_mix")
    assert a.tolist() == pytest.approx(
        [1.0 / 3.0, 2.0 / 3.0, 1.0, 1.0, 1.0, 2.0 / 3.0, 1.0 / 3.0]
    )
    assert positions.tolist() == [
        "onset",
        "onset",
        "interior",
        "interior",
        "interior",
        "offset",
        "offset",
    ]


def test_abrupt_multipliers_and_positions() -> None:
    a, positions = ramp_multipliers(5, ramp_rows=3, mode="abrupt")
    assert a.tolist() == [1.0, 1.0, 1.0, 1.0, 1.0]
    assert positions.tolist() == [
        "onset",
        "interior",
        "interior",
        "interior",
        "offset",
    ]


def test_abrupt_single_row_is_an_onset() -> None:
    a, positions = ramp_multipliers(1, mode="abrupt")
    assert a.tolist() == [1.0]
    assert positions.tolist() == ["onset"]


def test_linear_mix_too_short_raises() -> None:
    with pytest.raises(ValueError, match="at least"):
        ramp_multipliers(6, ramp_rows=3, mode="linear_mix")
    # 2 * ramp_rows + 1 = 7 is the minimum.
    a, positions = ramp_multipliers(7, ramp_rows=3, mode="linear_mix")
    assert a.tolist() == [0.25, 0.5, 0.75, 1.0, 0.75, 0.5, 0.25]
    assert positions[0] == "onset"
    assert positions[-1] == "offset"


def test_invalid_arguments_raise() -> None:
    with pytest.raises(ValueError, match="mode"):
        ramp_multipliers(9, mode="quadratic")
    with pytest.raises(ValueError, match="ramp_rows"):
        ramp_multipliers(9, ramp_rows=0)
    with pytest.raises(ValueError, match="n_rows"):
        ramp_multipliers(0)
    with pytest.raises(TypeError, match="n_rows"):
        ramp_multipliers(9.0)
    with pytest.raises(TypeError, match="ramp_rows"):
        ramp_multipliers(9, ramp_rows=3.0)


def test_attack_and_effective_row_masks() -> None:
    assert ATTACK_THRESHOLD == 0.0
    assert EFFECTIVE_THRESHOLD == 0.5

    a, _ = ramp_multipliers(9, ramp_rows=3, mode="linear_mix")
    assert attack_row_mask(a).tolist() == [True] * 9
    effective = effective_row_mask(a)
    assert effective.tolist() == [
        False,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        False,
    ]
    assert effective.sum() == 7

    abrupt, _ = ramp_multipliers(5, mode="abrupt")
    assert attack_row_mask(abrupt).all()
    assert effective_row_mask(abrupt).all()


def test_mask_helpers_validate_input() -> None:
    with pytest.raises(ValueError, match="one-dimensional"):
        attack_row_mask(np.ones((2, 2)))
    with pytest.raises(ValueError, match="finite"):
        effective_row_mask(np.array([1.0, np.nan]))
