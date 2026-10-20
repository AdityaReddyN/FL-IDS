"""Schema and content fingerprints for row tables.

The content fingerprint is independent of Parquet file metadata (compression,
writer version, pandas metadata). It hashes column-by-column with NumPy/Arrow;
no Python row loops are used.

Encoding rules
--------------
* Row order is part of the fingerprint.
* ``-0.0`` is normalised to ``0.0``.
* Every NaN is replaced by one canonical quiet-NaN bit pattern
  (``0x7ff8000000000000``) before hashing, so different NaN payloads match.
* Floats are hashed as little-endian ``float64``.
* Integers are hashed as a null mask followed by little-endian ``int64``.
* Strings are hashed as UTF-8 with an explicit length prefix: the length block
  (little-endian ``int64`` per string) precedes the concatenated UTF-8 bytes,
  plus a validity mask for nulls.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pyarrow as pa

CONTENT_DOMAIN = b"flids-content-v1"
SCHEMA_DOMAIN = b"flids-schema-v1"
CANONICAL_NAN = np.frombuffer(
    b"\x00\x00\x00\x00\x00\x00\xf8\x7f", dtype="<f8"
)[0]


def _update_token(hasher: "hashlib._Hash", token: bytes) -> None:
    hasher.update(len(token).to_bytes(8, "little"))
    hasher.update(token)


def _column_kind(series: pd.Series) -> str:
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return "bool"
    if pd.api.types.is_integer_dtype(dtype):
        return "int"
    if pd.api.types.is_float_dtype(dtype):
        return "float"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    if pd.api.types.is_string_dtype(dtype) or dtype == object:
        return "string"
    raise TypeError(f"unsupported column dtype for fingerprinting: {dtype!r}")


def _encode_bool(series: pd.Series) -> bytes:
    mask = series.isna().to_numpy(dtype=bool)
    values = series.to_numpy(dtype=bool, na_value=False).astype(np.uint8)
    return mask.tobytes() + values.tobytes()


def _encode_int(series: pd.Series) -> bytes:
    mask = series.isna().to_numpy(dtype=bool)
    values = series.to_numpy(dtype="int64", na_value=0).astype("<i8", copy=False)
    return mask.tobytes() + values.tobytes()


def _encode_datetime(series: pd.Series) -> bytes:
    mask = series.isna().to_numpy(dtype=bool)
    values = series.to_numpy(dtype="datetime64[ns]").astype("<i8", copy=False)
    return mask.tobytes() + values.tobytes()


def _encode_float(series: pd.Series) -> bytes:
    values = series.to_numpy(dtype="float64", na_value=np.nan).copy()
    values[values == 0.0] = 0.0
    values[np.isnan(values)] = CANONICAL_NAN
    return values.astype("<f8", copy=False).tobytes(order="C")


def _encode_string(series: pd.Series) -> bytes:
    array = pa.Array.from_pandas(series, type=pa.string())
    if isinstance(array, pa.ChunkedArray):
        array = array.combine_chunks()
    validity, offsets_buffer, data_buffer = array.buffers()

    validity_bytes = validity.to_pybytes() if validity is not None else b""
    if offsets_buffer is not None:
        offsets = np.frombuffer(offsets_buffer, dtype="<i4")
        lengths = np.diff(offsets).astype("<i8")
    else:
        lengths = np.zeros(0, dtype="<i8")
    data_bytes = data_buffer.to_pybytes() if data_buffer is not None else b""

    return b"".join(
        (
            int(array.null_count).to_bytes(8, "little"),
            len(validity_bytes).to_bytes(8, "little"),
            validity_bytes,
            lengths.tobytes(),
            len(data_bytes).to_bytes(8, "little"),
            data_bytes,
        )
    )


_ENCODERS = {
    "bool": _encode_bool,
    "int": _encode_int,
    "float": _encode_float,
    "datetime": _encode_datetime,
    "string": _encode_string,
}


def content_fingerprint(df: pd.DataFrame) -> str:
    """Return a SHA-256 hex digest of the table's schema-independent content."""
    hasher = hashlib.sha256()
    hasher.update(CONTENT_DOMAIN)
    hasher.update(len(df).to_bytes(8, "little"))
    hasher.update(len(df.columns).to_bytes(8, "little"))

    for name in df.columns:
        _update_token(hasher, str(name).encode("utf-8"))
        series = df[name]
        kind = _column_kind(series)
        _update_token(hasher, kind.encode("ascii"))
        payload = _ENCODERS[kind](series)
        hasher.update(len(payload).to_bytes(8, "little"))
        hasher.update(payload)

    return hasher.hexdigest()


def schema_fingerprint(df: pd.DataFrame) -> str:
    """Return a SHA-256 hex digest of ordered column names and pandas dtypes."""
    pairs = [[str(name), str(df[name].dtype)] for name in df.columns]
    payload = json.dumps(pairs, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(SCHEMA_DOMAIN + payload.encode("utf-8")).hexdigest()
