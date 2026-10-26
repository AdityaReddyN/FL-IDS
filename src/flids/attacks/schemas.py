"""Output table schemas for Stage 1 attack generation.

Each table's columns are defined in exactly one ordered dictionary. The
validator, the empty-table writer, and the tests all read those dictionaries,
so there is a single source of truth for names, dtypes, nullability, and
enumerated string values.

``attacked_rows.ramp_multiplier`` and ``step_labels.ramp_multiplier`` store
the **realized** multiplier ``a_t`` (``a_t * g_t`` for gradual deviation), the
same value used for the effective-row rule (D-023/D-024). The ``windows``
table stores per-window truth labels and strata for one segment.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .windows import WINDOW_LABELS, WINDOW_STRATA

FEATURE_FIELDS: tuple[str, ...] = (
    "lat",
    "lon",
    "velocity",
    "heading",
    "vertrate",
    "baroaltitude",
    "geoaltitude",
)

EPISODE_POSITIONS: tuple[str, ...] = ("none", "onset", "interior", "offset")
ONSET_MODES: tuple[str, ...] = ("linear_mix", "abrupt")


@dataclass(frozen=True)
class ColumnSpec:
    """Canonical dtype, nullability, and optional allowed values."""

    dtype: str
    nullable: bool = False
    allowed: tuple[str, ...] | None = None


ATTACKED_ROWS_SCHEMA: dict[str, ColumnSpec] = {
    "row_id": ColumnSpec("int64"),
    "source_row_id": ColumnSpec("int64"),
    "icao24": ColumnSpec("str"),
    "segment_id": ColumnSpec("int32"),
    "time": ColumnSpec("int64"),
    "segment_row_offset": ColumnSpec("int32"),
    "split": ColumnSpec("str"),
    **{f"orig_{field}": ColumnSpec("float64", nullable=True) for field in FEATURE_FIELDS},
    **{f"mod_{field}": ColumnSpec("float64", nullable=True) for field in FEATURE_FIELDS},
    # Nullable: a null onground row is ineligible for every family (D-038) and
    # the null is carried through to the output rather than coerced to True.
    "onground": ColumnSpec("bool", nullable=True),
    # The cleaned table derives this from lastcontact and marks nulls separately.
    "contact_lag_seconds": ColumnSpec("float64", nullable=True),
    "contact_lag_missing": ColumnSpec("bool"),
    "is_attack_row": ColumnSpec("bool"),
    "attack_family": ColumnSpec("str", nullable=True),
    "attack_subtype": ColumnSpec("str", nullable=True),
    "tier": ColumnSpec("str", nullable=True),
    "episode_id": ColumnSpec("int64", nullable=True),
    "episode_position": ColumnSpec("str", allowed=EPISODE_POSITIONS),
    "ramp_multiplier": ColumnSpec("float32"),
    "replay_source_row_id": ColumnSpec("int64", nullable=True),
    "replay_delay_seconds": ColumnSpec("float32", nullable=True),
}

STEP_LABELS_SCHEMA: dict[str, ColumnSpec] = {
    "source_row_id": ColumnSpec("int64"),
    "episode_id": ColumnSpec("int64", nullable=True),
    "is_attack_row": ColumnSpec("bool"),
    "attack_family": ColumnSpec("str", nullable=True),
    "attack_subtype": ColumnSpec("str", nullable=True),
    "tier": ColumnSpec("str", nullable=True),
    "episode_position": ColumnSpec("str", allowed=EPISODE_POSITIONS),
    "ramp_multiplier": ColumnSpec("float32"),
}

EPISODES_SCHEMA: dict[str, ColumnSpec] = {
    "episode_id": ColumnSpec("int64"),
    "overlay_key": ColumnSpec("str"),
    "icao24": ColumnSpec("str"),
    "segment_id": ColumnSpec("int32"),
    "split": ColumnSpec("str"),
    "attack_family": ColumnSpec("str"),
    "attack_subtype": ColumnSpec("str"),
    "tier": ColumnSpec("str"),
    "onset_mode": ColumnSpec("str", allowed=ONSET_MODES),
    "duration_seconds_requested": ColumnSpec("float64"),
    "n_rows": ColumnSpec("int32"),
    "start_row_offset": ColumnSpec("int32"),
    "end_row_offset": ColumnSpec("int32"),
    "start_time": ColumnSpec("int64"),
    "end_time": ColumnSpec("int64"),
    "start_source_row_id": ColumnSpec("int64"),
    "end_source_row_id": ColumnSpec("int64"),
    "grid_cell_id": ColumnSpec("str"),
    "speed_band": ColumnSpec("str"),
    "altitude_variant": ColumnSpec("str", nullable=True),
    "horizontal_magnitude_m": ColumnSpec("float64", nullable=True),
    "bearing_deg": ColumnSpec("float64", nullable=True),
    "shared_altitude_shift_m": ColumnSpec("float64", nullable=True),
    "gaussian_sigma_m": ColumnSpec("float64", nullable=True),
    "eq12_kappa": ColumnSpec("float64", nullable=True),
    "replay_delay_seconds_requested": ColumnSpec("float64", nullable=True),
    "replay_delay_seconds_effective": ColumnSpec("float64", nullable=True),
    "freeze_anchor_source_row_id": ColumnSpec("int64", nullable=True),
    "selection_method": ColumnSpec("str"),
    "tau_requested": ColumnSpec("float64"),
    "dataset_mode": ColumnSpec("str"),
    "seed_derivation": ColumnSpec("str"),
    "parameters_json": ColumnSpec("str"),
    "accepted": ColumnSpec("bool"),
    "rejection_reason": ColumnSpec("str", nullable=True),
}

REJECTED_CANDIDATES_SCHEMA: dict[str, ColumnSpec] = {
    "candidate_id": ColumnSpec("int64"),
    "overlay_key": ColumnSpec("str"),
    "icao24": ColumnSpec("str"),
    "segment_id": ColumnSpec("int32"),
    "split": ColumnSpec("str"),
    "attack_family": ColumnSpec("str"),
    "attack_subtype": ColumnSpec("str"),
    "tier": ColumnSpec("str"),
    "requested_start_row_offset": ColumnSpec("int32"),
    "requested_n_rows": ColumnSpec("int32"),
    "stage": ColumnSpec("str"),
    "reason": ColumnSpec("str"),
    "details_json": ColumnSpec("str"),
}

MODIFIED_ROW_PROVENANCE_SCHEMA: dict[str, ColumnSpec] = {
    "source_row_id": ColumnSpec("int64"),
    "episode_id": ColumnSpec("int64"),
    "changed_fields_json": ColumnSpec("str"),
    "orig_values_json": ColumnSpec("str"),
    "mod_values_json": ColumnSpec("str"),
    "ramp_multiplier": ColumnSpec("float32"),
    "validation_status": ColumnSpec("str"),
}

WINDOWS_SCHEMA: dict[str, ColumnSpec] = {
    "window_id": ColumnSpec("int64"),
    "icao24": ColumnSpec("str"),
    "segment_id": ColumnSpec("int32"),
    "split": ColumnSpec("str"),
    "start_offset": ColumnSpec("int32"),
    "n_rows": ColumnSpec("int32"),
    "label": ColumnSpec("str", allowed=WINDOW_LABELS),
    "stratum": ColumnSpec("str", allowed=WINDOW_STRATA),
    "n_attack_rows": ColumnSpec("int32"),
    "n_effective_rows": ColumnSpec("int32"),
    "episode_id": ColumnSpec("int64"),
    "attack_family": ColumnSpec("str", nullable=True),
    "attack_subtype": ColumnSpec("str", nullable=True),
    "tier": ColumnSpec("str", nullable=True),
}

SEGMENTS_SCHEMA: dict[str, ColumnSpec] = {
    "icao24": ColumnSpec("str"),
    "segment_id": ColumnSpec("int32"),
    "split": ColumnSpec("str"),
    "n_rows": ColumnSpec("int32"),
    "cell_id": ColumnSpec("str"),
    "n_eligible_starts": ColumnSpec("int32"),
    "eligible": ColumnSpec("bool"),
    "selection_u": ColumnSpec("float64"),
    "selected": ColumnSpec("bool"),
}

OVERLAY_SELECTIONS_SCHEMA: dict[str, ColumnSpec] = {
    "icao24": ColumnSpec("str"),
    "segment_id": ColumnSpec("int32"),
    "split": ColumnSpec("str"),
    "overlay_key": ColumnSpec("str"),
    "attack_family": ColumnSpec("str"),
    "tier": ColumnSpec("str"),
    "n_eligible_starts": ColumnSpec("int32"),
    "eligible": ColumnSpec("bool"),
    "selection_u": ColumnSpec("float64"),
    "tau_requested": ColumnSpec("float64"),
    "selected": ColumnSpec("bool"),
    "chosen": ColumnSpec("bool"),
}

TABLES: dict[str, dict[str, ColumnSpec]] = {
    "attacked_rows": ATTACKED_ROWS_SCHEMA,
    "step_labels": STEP_LABELS_SCHEMA,
    "episodes": EPISODES_SCHEMA,
    "rejected_candidates": REJECTED_CANDIDATES_SCHEMA,
    "modified_row_provenance": MODIFIED_ROW_PROVENANCE_SCHEMA,
    "windows": WINDOWS_SCHEMA,
    "segments": SEGMENTS_SCHEMA,
    "overlay_selections": OVERLAY_SELECTIONS_SCHEMA,
}
TABLE_NAMES: tuple[str, ...] = tuple(TABLES)


class SchemaError(ValueError):
    """Raised when a table does not match its declared schema."""


def _schema(table_name: str) -> dict[str, ColumnSpec]:
    try:
        return TABLES[table_name]
    except KeyError as error:
        raise KeyError(
            f"unknown table {table_name!r}; expected one of {TABLE_NAMES}"
        ) from error


def _pandas_dtype(spec: ColumnSpec):
    if spec.dtype == "int64":
        return pd.Int64Dtype() if spec.nullable else np.int64
    if spec.dtype == "int32":
        return pd.Int32Dtype() if spec.nullable else np.int32
    if spec.dtype == "float64":
        return pd.Float64Dtype() if spec.nullable else np.float64
    if spec.dtype == "float32":
        return pd.Float32Dtype() if spec.nullable else np.float32
    if spec.dtype == "bool":
        return pd.BooleanDtype() if spec.nullable else bool
    if spec.dtype == "str":
        return pd.StringDtype()
    raise SchemaError(f"unknown canonical dtype {spec.dtype!r}")


_ARROW_TYPES = {
    "int64": pa.int64(),
    "int32": pa.int32(),
    "float64": pa.float64(),
    "float32": pa.float32(),
    "bool": pa.bool_(),
    "str": pa.string(),
}

_DTYPE_NAMES = {
    "int64": {"int64", "Int64"},
    "int32": {"int32", "Int32"},
    "float64": {"float64", "Float64"},
    "float32": {"float32", "Float32"},
    "bool": {"bool", "boolean"},
}


def _arrow_schema(table_name: str) -> pa.Schema:
    schema = _schema(table_name)
    return pa.schema(
        [(name, _ARROW_TYPES[spec.dtype]) for name, spec in schema.items()]
    )


def _dtype_matches(dtype, spec: ColumnSpec) -> bool:
    if spec.dtype == "str":
        return bool(pd.api.types.is_string_dtype(dtype)) or dtype == object
    return str(dtype) in _DTYPE_NAMES[spec.dtype]


def empty_table(table_name: str) -> pd.DataFrame:
    """Return an empty DataFrame with the declared columns and dtypes."""
    schema = _schema(table_name)
    return pd.DataFrame(
        {
            name: pd.Series([], dtype=_pandas_dtype(spec))
            for name, spec in schema.items()
        }
    )


def validate_table(df: pd.DataFrame, table_name: str) -> None:
    """Validate column names, dtypes, nullability, and enumerated values."""
    schema = _schema(table_name)
    missing = [name for name in schema if name not in df.columns]
    extra = [name for name in df.columns if name not in schema]
    if missing or extra:
        parts = []
        if missing:
            parts.append("missing column(s): " + ", ".join(missing))
        if extra:
            parts.append("extra column(s): " + ", ".join(extra))
        raise SchemaError(f"{table_name}: " + "; ".join(parts))

    for name, spec in schema.items():
        series = df[name]
        if not _dtype_matches(series.dtype, spec):
            raise SchemaError(
                f"{table_name}.{name}: dtype {series.dtype!r} does not match "
                f"{spec.dtype!r}"
            )
        if not spec.nullable and series.isna().any():
            raise SchemaError(
                f"{table_name}.{name}: null value in non-nullable column"
            )
        if spec.allowed is not None:
            disallowed = sorted(
                set(series.dropna().astype(str)) - set(spec.allowed)
            )
            if disallowed:
                raise SchemaError(
                    f"{table_name}.{name}: disallowed value(s) {disallowed}; "
                    f"expected one of {list(spec.allowed)}"
                )


def write_empty_table(path: str | Path, table_name: str) -> None:
    """Write a zero-row Parquet file with the declared schema."""
    table = pa.Table.from_pandas(
        empty_table(table_name),
        schema=_arrow_schema(table_name),
        preserve_index=False,
    )
    pq.write_table(table, Path(path))
