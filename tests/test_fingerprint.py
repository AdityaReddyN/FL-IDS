import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from flids.attacks.fingerprint import content_fingerprint, schema_fingerprint


def sample_table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "icao24": ["abc123", "def456"],
            "time": np.array([10, 20], dtype=np.int64),
            "lat": np.array([1.5, -2.25], dtype=np.float64),
            "onground": np.array([True, False], dtype=bool),
        }
    )


def write_parquet(df: pd.DataFrame, path, compression: str) -> None:
    pq.write_table(
        pa.Table.from_pandas(df, preserve_index=False),
        path,
        compression=compression,
    )


def test_content_fingerprint_ignores_parquet_compression(tmp_path) -> None:
    df = sample_table()
    snappy = tmp_path / "snappy.parquet"
    gzip = tmp_path / "gzip.parquet"
    write_parquet(df, snappy, "snappy")
    write_parquet(df, gzip, "gzip")

    assert snappy.read_bytes() != gzip.read_bytes()
    assert content_fingerprint(pd.read_parquet(snappy)) == content_fingerprint(
        pd.read_parquet(gzip)
    )


def test_content_fingerprint_changes_with_one_value() -> None:
    first = sample_table()
    second = first.copy()
    second.loc[1, "lat"] = -2.2500001
    assert content_fingerprint(first) != content_fingerprint(second)


def test_negative_zero_and_positive_zero_are_equal() -> None:
    positive = sample_table()
    negative = sample_table()
    positive["lat"] = np.array([0.0, 1.0])
    negative["lat"] = np.array([-0.0, 1.0])
    assert content_fingerprint(positive) == content_fingerprint(negative)


def test_all_nan_payloads_are_canonicalised() -> None:
    payload_nan = np.frombuffer(
        b"\x01\x00\x00\x00\x00\x00\xf8\x7f", dtype="<f8"
    )[0]
    first = sample_table()
    second = sample_table()
    first["lat"] = np.array([np.nan, 1.0])
    second["lat"] = np.array([payload_nan, 1.0])
    assert np.isnan(payload_nan)
    assert content_fingerprint(first) == content_fingerprint(second)


def test_row_order_is_part_of_fingerprint() -> None:
    df = sample_table()
    assert content_fingerprint(df) != content_fingerprint(
        df.iloc[::-1].reset_index(drop=True)
    )


def test_string_length_prefix_prevents_concatenation_collision() -> None:
    first = sample_table().iloc[[0]].copy()
    second = sample_table().iloc[[0]].copy()
    first["icao24"] = ["ab"]
    second["icao24"] = ["a"]
    first = pd.concat([first, first.assign(icao24="c")], ignore_index=True)
    second = pd.concat([second, second.assign(icao24="bc")], ignore_index=True)
    assert content_fingerprint(first) != content_fingerprint(second)


def test_schema_fingerprint_ignores_compression_changes_dtype(tmp_path) -> None:
    df = sample_table()
    snappy = tmp_path / "a.parquet"
    gzip = tmp_path / "b.parquet"
    write_parquet(df, snappy, "snappy")
    write_parquet(df, gzip, "gzip")
    assert schema_fingerprint(pd.read_parquet(snappy)) == schema_fingerprint(
        pd.read_parquet(gzip)
    )

    retyped = df.copy()
    retyped["time"] = retyped["time"].astype(np.int32)
    assert schema_fingerprint(df) != schema_fingerprint(retyped)


def test_nullable_integers_hash_null_mask_and_values() -> None:
    first = pd.DataFrame({"x": pd.Series([1, None], dtype="Int64")})
    second = pd.DataFrame({"x": pd.Series([1, 2], dtype="Int64")})
    assert content_fingerprint(first) != content_fingerprint(second)


def test_schema_fingerprint_canonicalises_string_dtypes() -> None:
    def frame(dtype) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "s": pd.Series(["alpha", "beta"], dtype=dtype),
                "x": np.array([1.0, 2.0], dtype=np.float64),
            }
        )

    fingerprints = {
        schema_fingerprint(frame(dtype))
        for dtype in (
            object,
            "str",
            "string",
            pd.StringDtype("pyarrow"),
        )
    }
    assert len(fingerprints) == 1

    base = frame(object)
    as_float32 = base.copy()
    as_float32["x"] = as_float32["x"].astype(np.float32)
    assert schema_fingerprint(base) != schema_fingerprint(as_float32)
