import numpy as np
import pandas as pd
import pytest

from flids.attacks.schemas import (
    TABLES,
    TABLE_NAMES,
    ColumnSpec,
    SchemaError,
    empty_table,
    validate_table,
    write_empty_table,
)
from flids.attacks.windows import WINDOW_LABELS, WINDOW_STRATA


def sample_value(name: str, spec: ColumnSpec):
    if spec.allowed:
        return spec.allowed[0]
    if spec.nullable:
        return None
    if spec.dtype in {"int64", "int32"}:
        return 1
    if spec.dtype in {"float64", "float32"}:
        return 1.0
    if spec.dtype == "bool":
        return False
    if spec.dtype == "str":
        return "x"
    raise AssertionError(name)


_TEST_DTYPES = {
    "int64": "Int64",
    "int32": "Int32",
    "float64": "Float64",
    "float32": "Float32",
    "bool": "boolean",
    "str": "string",
}


def one_valid_row(table_name: str, **overrides) -> pd.DataFrame:
    schema = TABLES[table_name]
    values = {name: sample_value(name, spec) for name, spec in schema.items()}
    values.update(overrides)
    return pd.DataFrame(
        {
            name: pd.Series([values[name]], dtype=_TEST_DTYPES[spec.dtype])
            for name, spec in schema.items()
        }
    )


@pytest.mark.parametrize("table_name", TABLE_NAMES)
def test_empty_table_matches_schema(table_name) -> None:
    schema = TABLES[table_name]
    df = empty_table(table_name)
    assert list(df.columns) == list(schema)
    validate_table(df, table_name)


@pytest.mark.parametrize("table_name", TABLE_NAMES)
def test_write_empty_table_round_trips(tmp_path, table_name) -> None:
    path = tmp_path / f"{table_name}.parquet"
    write_empty_table(path, table_name)
    loaded = pd.read_parquet(path)
    assert list(loaded.columns) == list(TABLES[table_name])
    validate_table(loaded, table_name)


def test_missing_column_is_rejected() -> None:
    df = empty_table("episodes").drop(columns=["seed_derivation"])
    with pytest.raises(SchemaError, match="missing"):
        validate_table(df, "episodes")


def test_extra_column_is_rejected() -> None:
    df = empty_table("episodes").assign(unexpected=1)
    with pytest.raises(SchemaError, match="extra"):
        validate_table(df, "episodes")


def test_wrong_dtype_is_rejected() -> None:
    df = empty_table("step_labels")
    df["source_row_id"] = df["source_row_id"].astype(np.int32)
    with pytest.raises(SchemaError, match="dtype"):
        validate_table(df, "step_labels")


def test_non_nullable_column_rejects_nulls() -> None:
    df = one_valid_row("episodes", episode_id=None)
    with pytest.raises(SchemaError, match="null"):
        validate_table(df, "episodes")


def test_disallowed_enum_value_is_rejected() -> None:
    df = one_valid_row("episodes", onset_mode="bogus")
    with pytest.raises(SchemaError, match="onset_mode"):
        validate_table(df, "episodes")


def test_windows_table_accepts_declared_labels_and_strata() -> None:
    for label in WINDOW_LABELS:
        for stratum in WINDOW_STRATA:
            df = one_valid_row(
                "windows", label=label, stratum=stratum
            )
            validate_table(df, "windows")


def test_windows_table_rejects_bad_label_and_stratum() -> None:
    with pytest.raises(SchemaError, match="label"):
        validate_table(
            one_valid_row("windows", label="maybe"), "windows"
        )
    with pytest.raises(SchemaError, match="stratum"):
        validate_table(
            one_valid_row("windows", stratum="edge"), "windows"
        )


def test_windows_table_is_registered() -> None:
    assert "windows" in TABLE_NAMES
    assert list(empty_table("windows").columns) == list(
        TABLES["windows"]
    )


def test_segments_table_is_registered() -> None:
    assert "segments" in TABLE_NAMES
    validate_table(one_valid_row("segments"), "segments")


def test_episodes_schema_uses_tau_requested_name() -> None:
    assert "tau_requested" in TABLES["episodes"]
    assert "eta_requested" not in TABLES["episodes"]
