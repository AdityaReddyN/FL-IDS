"""Episode assembly for one segment (D-024).

``build_episode`` composes the D-022/D-023 primitives into one episode. It is
pure and in-memory: it never reads the YAML, never writes a file, and never
mutates ``segment_values``, ``times``, the eligibility mask, the replay source
offsets, or the RNG's already-consumed state beyond the episode's own draws.

Only the fields selected by ``spec.attack_family`` are modified; metadata such
as ``onground``, ``contact_lag_*`` and the ``*_missing`` flags is never read or
returned. All expected failures are *rejections* (``accepted=False`` with a
``reason``), never exceptions:

* ``latitude_out_of_range`` / ``altitude_out_of_range`` from the primitives
* ``no_replay_source`` (defensive: placement should already prevent it; the
  builder logs a warning when it fires)
* ``no_freeze_anchor``
* ``insufficient_effective_rows`` (fewer than five realized ``a_t >= 0.5``)
* ``replay_delay_mismatch`` (an active row misses the requested delay by more
  than the tolerance)
* ``no_measurable_change`` (provisional no-op guard, see below)

A rejected result returns copies of the original target fields, empty
``changed_fields``, and zero displacement arrays.

No-op guard (provisional, D-024)
--------------------------------
``NOOP_MIN_HORIZONTAL_M = 100.0`` and ``NOOP_MIN_ALTITUDE_M = 30.0``. The
maximum is taken over *effective* rows only. Horizontal families, freeze, and
replay use :func:`detectability.injected_displacement_m`; the altitude family
uses the absolute altitude change; replay counts both its horizontal and
altitude change, and full-field replay counts any field that moves the
aircraft horizontally or vertically. An episode below its threshold is
rejected with ``"no_measurable_change"`` so that a stationary aircraft cannot
produce an unmeasurable "attack". These thresholds are provisional.

Effective rows are always evaluated against the **realized** multipliers
(``a_t * g_t`` for gradual deviation), as in D-023. Gradual episodes therefore
need enough rows to realize at least five effective rows; shorter candidates
are rejected with ``"insufficient_effective_rows"``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from .detectability import injected_displacement_m
from .freeze import anchor_from_offsets, freeze_lat_lon
from .manipulation import (
    add_scaled_eq12_noise,
    altitude_constant,
    apply_horizontal_displacement,
    horizontal_displacement_constant,
    horizontal_displacement_gaussian,
    manipulation_streams,
)
from .ramps import MODES as ONSET_MODES, ramp_multipliers
from .replay import (
    FULL_REPLAY_FIELDS,
    PARTIAL_REPLAY_FIELDS,
    replay_fields,
)

ATTACK_FAMILIES: tuple[str, ...] = (
    "constant_deviation",
    "random_gaussian_deviation",
    "gradual_deviation",
    "altitude_constant_deviation",
    "replay_partial_field",
    "replay_full_field",
    "freeze_fixed_value",
)
HORIZONTAL_FAMILIES: tuple[str, ...] = (
    "constant_deviation",
    "random_gaussian_deviation",
    "gradual_deviation",
)
ALTITUDE_FAMILY = "altitude_constant_deviation"
REPLAY_PARTIAL_FAMILY = "replay_partial_field"
REPLAY_FULL_FAMILY = "replay_full_field"
FREEZE_FAMILY = "freeze_fixed_value"
REPLAY_FAMILIES: tuple[str, ...] = (
    REPLAY_PARTIAL_FAMILY,
    REPLAY_FULL_FAMILY,
)
ALTITUDE_VARIANTS: tuple[str, ...] = ("baro_only", "baro_plus_geo")

MIN_EFFECTIVE_ROWS = 5
NOOP_MIN_HORIZONTAL_M = 100.0
NOOP_MIN_ALTITUDE_M = 30.0
EFFECTIVE_THRESHOLD = 0.5

FROZEN_ANCHOR_MAX_AGE_SECONDS = 30.0

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EpisodeSpec:
    """Everything one episode needs, passed explicitly (never read from YAML)."""

    attack_family: str
    tier: str
    subtype: str | None = None
    altitude_variant: str | None = None
    onset_mode: str = "linear_mix"
    ramp_rows: int = 3
    magnitude_m: float | None = None
    bearing_deg: float | None = None
    sigma_m: float | None = None
    kappa: float = 0.0
    per_step_sigma_m: float = 25.0
    shift_m: float | None = None
    replay_delay_s: float = 300.0
    replay_tolerance_s: float = 5.0


@dataclass(frozen=True)
class EpisodeResult:
    """Outcome of one candidate episode.

    ``values`` holds episode-length arrays for the family's target fields.
    ``multipliers`` and ``positions`` are episode-length; multipliers are the
    realized ones. ``delays`` is episode-length for replay and ``None``
    otherwise. ``changed_fields`` lists the fields that actually changed on
    each row.
    """

    accepted: bool
    reason: str | None
    start_offset: int
    n_rows: int
    values: dict[str, np.ndarray]
    multipliers: np.ndarray
    positions: np.ndarray
    delays: np.ndarray | None
    changed_fields: tuple[tuple[str, ...], ...]
    horizontal_displacement_m: np.ndarray
    altitude_change_m: np.ndarray
    summary: dict
    anchor_offset: int | None = None


def _finite_number(value, name: str, minimum=None) -> float:
    if value is None:
        raise ValueError(f"{name} is required for this attack family")
    number = float(value)
    if not np.isfinite(number):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and number < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return number


def _validate_spec(spec: EpisodeSpec) -> None:
    if spec.attack_family not in ATTACK_FAMILIES:
        raise ValueError(
            f"attack_family must be one of {ATTACK_FAMILIES!r}; "
            f"got {spec.attack_family!r}"
        )
    if spec.onset_mode not in ONSET_MODES:
        raise ValueError(
            f"onset_mode must be one of {ONSET_MODES!r}; "
            f"got {spec.onset_mode!r}"
        )
    if (
        not isinstance(spec.ramp_rows, (int, np.integer))
        or isinstance(spec.ramp_rows, bool)
        or spec.ramp_rows < 1
    ):
        raise ValueError("ramp_rows must be a positive integer")

    family = spec.attack_family
    if family in HORIZONTAL_FAMILIES:
        if family != "random_gaussian_deviation":
            _finite_number(spec.magnitude_m, "magnitude_m", minimum=0.0)
            bearing = _finite_number(spec.bearing_deg, "bearing_deg")
            if not 0.0 <= bearing < 360.0:
                raise ValueError("bearing_deg must be in [0, 360)")
        _finite_number(spec.kappa, "kappa", minimum=0.0)
        _finite_number(
            spec.per_step_sigma_m, "per_step_sigma_m", minimum=0.0
        )
        if family == "random_gaussian_deviation":
            _finite_number(spec.sigma_m, "sigma_m", minimum=0.0)
    elif family == ALTITUDE_FAMILY:
        _finite_number(spec.shift_m, "shift_m")
        if spec.altitude_variant not in ALTITUDE_VARIANTS:
            raise ValueError(
                "altitude_variant must be one of "
                f"{ALTITUDE_VARIANTS!r}; got {spec.altitude_variant!r}"
            )
    elif family in REPLAY_FAMILIES:
        _finite_number(spec.replay_delay_s, "replay_delay_s", minimum=0.0)
        _finite_number(
            spec.replay_tolerance_s,
            "replay_tolerance_s",
            minimum=0.0,
        )


def _family_fields(spec: EpisodeSpec) -> tuple[str, ...]:
    family = spec.attack_family
    if family in HORIZONTAL_FAMILIES or family == FREEZE_FAMILY:
        return ("lat", "lon")
    if family == ALTITUDE_FAMILY:
        if spec.altitude_variant == "baro_plus_geo":
            return ("baroaltitude", "geoaltitude")
        return ("baroaltitude",)
    if family == REPLAY_PARTIAL_FAMILY:
        return PARTIAL_REPLAY_FIELDS
    if family == REPLAY_FULL_FAMILY:
        return FULL_REPLAY_FIELDS
    raise AssertionError(family)


def _one_dimensional(values, name: str) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    return array


def _segment_field(segment_values, name: str, length: int) -> np.ndarray:
    if name not in segment_values:
        raise KeyError(f"segment_values is missing {name!r}")
    array = np.asarray(segment_values[name], dtype=float)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if array.size != length:
        raise ValueError(f"{name} must have the same length as times")
    return array


def _random_generators(spec: EpisodeSpec, episode_rng):
    if spec.attack_family == "random_gaussian_deviation":
        if episode_rng is None or not hasattr(episode_rng, "spawn"):
            raise ValueError("episode_rng is required for Gaussian episodes")
        return manipulation_streams(episode_rng)
    if spec.kappa > 0.0:
        if episode_rng is None or not hasattr(episode_rng, "spawn"):
            raise ValueError(
                "episode_rng is required when kappa > 0"
            )
        return manipulation_streams(episode_rng)
    return None, None


def _changed_fields(
    originals: dict[str, np.ndarray],
    modified: dict[str, np.ndarray],
    fields: tuple[str, ...],
    active: np.ndarray,
) -> tuple[tuple[str, ...], ...]:
    changed = {name: np.zeros(active.size, dtype=bool) for name in fields}
    for name in fields:
        before = originals[name]
        after = modified[name]
        same = (before == after) | (
            np.isnan(before) & np.isnan(after)
        )
        changed[name] = active & ~same
    return tuple(
        tuple(name for name in fields if changed[name][row])
        for row in range(active.size)
    )


def _summary(
    multipliers: np.ndarray,
    horizontal: np.ndarray,
    altitude: np.ndarray,
    delays: np.ndarray | None,
) -> dict:
    effective = multipliers >= EFFECTIVE_THRESHOLD
    if np.any(effective):
        horizontal_max = float(np.max(horizontal[effective]))
        altitude_max = float(np.max(altitude[effective]))
    else:
        horizontal_max = 0.0
        altitude_max = 0.0

    delay_max = None
    if delays is not None:
        finite = delays[np.isfinite(delays)]
        if finite.size:
            delay_max = float(np.max(finite))
    return {
        "n_rows": int(multipliers.size),
        "n_attack_rows": int(np.count_nonzero(multipliers > 0.0)),
        "n_effective_rows": int(np.count_nonzero(effective)),
        "max_horizontal_displacement_m": horizontal_max,
        "max_altitude_change_m": altitude_max,
        "max_achieved_delay_s": delay_max,
    }


def _rejected(
    segment_values,
    fields: tuple[str, ...],
    start: int,
    stop: int,
    multipliers: np.ndarray | None,
    positions: np.ndarray,
    reason: str,
    delays: np.ndarray | None = None,
) -> EpisodeResult:
    n_rows = stop - start
    values = {
        name: np.array(
            segment_values[name][start:stop], dtype=float, copy=True
        )
        for name in fields
    }
    if multipliers is None:
        multipliers = np.zeros(n_rows)
    zeros = np.zeros(n_rows)
    return EpisodeResult(
        accepted=False,
        reason=reason,
        start_offset=start,
        n_rows=n_rows,
        values=values,
        multipliers=multipliers,
        positions=positions,
        delays=delays,
        changed_fields=tuple(() for _ in range(n_rows)),
        horizontal_displacement_m=zeros.copy(),
        altitude_change_m=zeros.copy(),
        summary=_summary(multipliers, zeros, zeros, delays),
    )


def _insufficient_rejection(segment_values, fields, start, stop, reason):
    n_rows = stop - start
    return _rejected(
        segment_values,
        fields,
        start,
        stop,
        None,
        np.full(n_rows, "none", dtype="<U8"),
        reason,
    )


def _horizontal_episode(
    spec: EpisodeSpec,
    segment_values,
    times,
    start,
    n_rows,
    episode_rng,
    multipliers,
):
    """Return ``(values, realized, reason)`` for a horizontal family."""
    lat_full = _segment_field(segment_values, "lat", times.size)
    lon_full = _segment_field(segment_values, "lon", times.size)
    lat = lat_full[start:start + n_rows]
    lon = lon_full[start:start + n_rows]

    if spec.attack_family == "gradual_deviation":
        fractions = (
            np.ones(1, dtype=float)
            if n_rows == 1
            else np.arange(n_rows, dtype=float) / (n_rows - 1)
        )
        realized = multipliers * fractions
    else:
        realized = multipliers

    gaussian_rng, eq12_rng = _random_generators(spec, episode_rng)
    if spec.attack_family == "random_gaussian_deviation":
        north, east = horizontal_displacement_gaussian(
            realized, spec.sigma_m, gaussian_rng
        )
    else:
        north, east = horizontal_displacement_constant(
            realized, spec.magnitude_m, spec.bearing_deg
        )
    if spec.kappa > 0.0:
        north, east = add_scaled_eq12_noise(
            north,
            east,
            realized,
            spec.kappa,
            spec.per_step_sigma_m,
            eq12_rng,
        )

    result = apply_horizontal_displacement(
        lat, lon, realized, north, east
    )
    if result.rejected:
        return None, realized, result.reason
    return {
        "lat": result.values["lat"],
        "lon": result.values["lon"],
    }, realized, None


def build_episode(
    segment_values,
    times,
    eligible_mask_for_family,
    replay_source_offsets_or_None,
    start_offset: int,
    n_rows: int,
    spec: EpisodeSpec,
    episode_rng,
) -> EpisodeResult:
    """Build one candidate episode inside a segment.

    ``start_offset`` and ``n_rows`` are segment-relative. For replay families,
    ``replay_source_offsets_or_None`` is a full-segment integer array whose
    entries are source row offsets (``-1`` means "no source"); only the
    episode's active rows are required to have a source. See the module
    docstring for the returned fields and the rejection contract.
    """
    _validate_spec(spec)

    if (
        not isinstance(start_offset, (int, np.integer))
        or isinstance(start_offset, bool)
    ):
        raise TypeError("start_offset must be an integer")
    if (
        not isinstance(n_rows, (int, np.integer))
        or isinstance(n_rows, bool)
    ):
        raise TypeError("n_rows must be an integer")
    if start_offset < 0:
        raise ValueError("start_offset must be non-negative")
    if n_rows < 1:
        raise ValueError("n_rows must be positive")

    time_values = np.asarray(times, dtype=float)
    if time_values.ndim != 1:
        raise ValueError("times must be one-dimensional")
    if not np.all(np.isfinite(time_values)):
        raise ValueError("times must contain only finite values")
    length = time_values.size
    stop = start_offset + n_rows
    if stop > length:
        raise ValueError(
            "the episode must lie inside the segment: "
            f"start {start_offset} + {n_rows} rows > {length}"
        )

    eligible = np.asarray(eligible_mask_for_family)
    if eligible.ndim != 1 or eligible.size != length:
        raise ValueError(
            "eligible_mask_for_family must be one-dimensional and match times"
        )
    eligible = eligible.astype(bool, copy=False)

    fields = _family_fields(spec)
    for name in fields:
        _segment_field(segment_values, name, length)

    replay_sources = None
    if spec.attack_family in REPLAY_FAMILIES:
        if replay_source_offsets_or_None is None:
            raise ValueError(
                "replay_source_offsets_or_None is required for replay families"
            )
        sources = np.asarray(replay_source_offsets_or_None)
        if sources.ndim != 1 or sources.size != length:
            raise ValueError(
                "replay source offsets must be one-dimensional and match times"
            )
        if not np.issubdtype(sources.dtype, np.integer):
            raise TypeError("replay source offsets must contain integers")
        replay_sources = sources.astype(np.int64, copy=True)

    try:
        multipliers, positions = ramp_multipliers(
            n_rows, spec.ramp_rows, spec.onset_mode
        )
    except ValueError:
        return _insufficient_rejection(
            segment_values,
            fields,
            start_offset,
            stop,
            "insufficient_effective_rows",
        )

    if spec.attack_family == "gradual_deviation":
        fractions = (
            np.ones(1, dtype=float)
            if n_rows == 1
            else np.arange(n_rows, dtype=float) / (n_rows - 1)
        )
        realized = multipliers * fractions
    else:
        realized = multipliers

    if np.count_nonzero(realized >= EFFECTIVE_THRESHOLD) < MIN_EFFECTIVE_ROWS:
        return _rejected(
            segment_values,
            fields,
            start_offset,
            stop,
            realized,
            positions,
            "insufficient_effective_rows",
        )

    if not np.all(eligible[start_offset:stop]):
        return _rejected(
            segment_values,
            fields,
            start_offset,
            stop,
            realized,
            positions,
            "ineligible_interval",
        )

    originals = {
        name: np.asarray(
            segment_values[name][start_offset:stop], dtype=float
        ).copy()
        for name in fields
    }
    delays = None
    reason = None
    freeze_anchor_offset = None

    if spec.attack_family in HORIZONTAL_FAMILIES:
        modified, realized, reason = _horizontal_episode(
            spec,
            segment_values,
            time_values,
            start_offset,
            n_rows,
            episode_rng,
            multipliers,
        )
        if reason is not None:
            return _rejected(
                segment_values,
                fields,
                start_offset,
                stop,
                realized,
                positions,
                reason,
            )
    elif spec.attack_family == ALTITUDE_FAMILY:
        baro_full = _segment_field(
            segment_values, "baroaltitude", length
        )
        geo_full = (
            _segment_field(segment_values, "geoaltitude", length)
            if spec.altitude_variant == "baro_plus_geo"
            else None
        )
        result = altitude_constant(
            baro_full[start_offset:stop],
            None if geo_full is None else geo_full[start_offset:stop],
            realized,
            spec.shift_m,
            spec.altitude_variant,
        )
        if result.rejected:
            return _rejected(
                segment_values,
                fields,
                start_offset,
                stop,
                realized,
                positions,
                result.reason,
            )
        modified = {
            "baroaltitude": result.values["baroaltitude"],
        }
        if spec.altitude_variant == "baro_plus_geo":
            modified["geoaltitude"] = result.values["geoaltitude"]
    elif spec.attack_family == FREEZE_FAMILY:
        lat_full = _segment_field(segment_values, "lat", length)
        lon_full = _segment_field(segment_values, "lon", length)
        anchor = anchor_from_offsets(
            lat_full,
            lon_full,
            eligible,
            start_offset,
            time_values,
            max_anchor_age_seconds=FROZEN_ANCHOR_MAX_AGE_SECONDS,
        )
        if anchor is None:
            return _rejected(
                segment_values,
                fields,
                start_offset,
                stop,
                realized,
                positions,
                "no_freeze_anchor",
            )
        freeze_anchor_offset = anchor[2]
        result = freeze_lat_lon(
            lat_full[start_offset:stop],
            lon_full[start_offset:stop],
            realized,
            anchor[0],
            anchor[1],
        )
        modified = {
            "lat": result.values["lat"],
            "lon": result.values["lon"],
        }
    else:
        full_values = {
            name: _segment_field(segment_values, name, length)
            for name in fields
        }
        full_multipliers = np.zeros(length)
        full_multipliers[start_offset:stop] = realized
        result = replay_fields(
            full_values,
            replay_sources,
            full_multipliers,
            fields,
            time_values,
        )
        if result.rejected:
            if result.reason == "no_replay_source":
                LOGGER.warning(
                    "defensive no_replay_source for episode at segment "
                    "offset %d; placement should have rejected this "
                    "candidate",
                    start_offset,
                )
            return _rejected(
                segment_values,
                fields,
                start_offset,
                stop,
                realized,
                positions,
                result.reason,
            )
        delays = result.delays[start_offset:stop]
        active = realized > 0.0
        mismatch = active & (
            np.abs(delays - spec.replay_delay_s)
            > spec.replay_tolerance_s
        )
        if np.any(mismatch):
            return _rejected(
                segment_values,
                fields,
                start_offset,
                stop,
                realized,
                positions,
                "replay_delay_mismatch",
                delays=delays,
            )
        modified = {
            name: result.values[name][start_offset:stop]
            for name in fields
        }

    active = realized > 0.0
    effective = realized >= EFFECTIVE_THRESHOLD

    horizontal = np.zeros(n_rows)
    if "lat" in fields and "lon" in fields:
        horizontal = injected_displacement_m(
            originals["lat"],
            originals["lon"],
            modified["lat"],
            modified["lon"],
        )

    altitude_change = np.zeros(n_rows)
    if spec.attack_family == ALTITUDE_FAMILY:
        altitude_change = np.abs(
            modified["baroaltitude"] - originals["baroaltitude"]
        )
    elif spec.attack_family in REPLAY_FAMILIES:
        candidates = [
            np.abs(modified[name] - originals[name])
            for name in ("baroaltitude", "geoaltitude")
            if name in fields
        ]
        if candidates:
            altitude_change = np.maximum.reduce(candidates)

    if np.any(effective):
        horizontal_max = float(np.max(horizontal[effective]))
        altitude_max = float(np.max(altitude_change[effective]))
    else:
        horizontal_max = 0.0
        altitude_max = 0.0

    if spec.attack_family in HORIZONTAL_FAMILIES or (
        spec.attack_family == FREEZE_FAMILY
    ):
        measurable = horizontal_max >= NOOP_MIN_HORIZONTAL_M
    elif spec.attack_family == ALTITUDE_FAMILY:
        measurable = altitude_max >= NOOP_MIN_ALTITUDE_M
    else:
        measurable = (
            horizontal_max >= NOOP_MIN_HORIZONTAL_M
            or altitude_max >= NOOP_MIN_ALTITUDE_M
        )
    if not measurable:
        return _rejected(
            segment_values,
            fields,
            start_offset,
            stop,
            realized,
            positions,
            "no_measurable_change",
            delays=delays,
        )

    return EpisodeResult(
        accepted=True,
        reason=None,
        start_offset=start_offset,
        n_rows=n_rows,
        values=modified,
        multipliers=realized,
        positions=positions,
        delays=delays,
        changed_fields=_changed_fields(
            originals, modified, fields, active
        ),
        horizontal_displacement_m=horizontal,
        altitude_change_m=altitude_change,
        summary=_summary(
            realized, horizontal, altitude_change, delays
        ),
        anchor_offset=freeze_anchor_offset,
    )
