"""Shared read-only access to the HDD OpenSky archives (``*.csv.tar``).

Each archive is a tar holding a gzipped CSV (``states_*.csv.gz``) plus
``README.txt``/``LICENSE.txt``. The inner CSV is decompressed on the fly and
never extracted to disk. Used by both ``scripts/audit_hdd_source.py`` and
``scripts/build_hdd_dataset.py`` so there is one archive reader.
"""

from __future__ import annotations

import gzip
import tarfile
from pathlib import Path

import pandas as pd

from .clean import RAW_COLUMNS

README_MAX_BYTES = 2048


def find_archives(input_dir: str | Path) -> list[Path]:
    """Every ``*.csv.tar`` under ``input_dir``, recursively and sorted.

    The archives live in nested, dot-prefixed per-date/hour directories
    (``data/hdd_data/.2019-11-18/00/states_2019-11-18-00.csv.tar``).
    """
    return sorted(Path(input_dir).rglob("*.csv.tar"))


def _csv_stream(tar: tarfile.TarFile, member: tarfile.TarInfo):
    handle = tar.extractfile(member)
    if handle is None:
        raise ValueError(f"cannot read member {member.name!r}")
    if member.name.lower().endswith(".gz"):
        return gzip.GzipFile(fileobj=handle)
    return handle


def _find_members(tar: tarfile.TarFile):
    csv_member = None
    readme_head = None
    for member in tar.getmembers():
        lower = member.name.lower()
        if (lower.endswith(".csv") or lower.endswith(".csv.gz")) and csv_member is None:
            csv_member = member
        elif "readme" in lower and readme_head is None:
            handle = tar.extractfile(member)
            if handle is not None:
                readme_head = handle.read(README_MAX_BYTES).decode("utf-8", "replace")
    if csv_member is None:
        raise ValueError("no .csv or .csv.gz member found in archive")
    return csv_member, readme_head


def read_archive(path: str | Path) -> tuple[str, pd.DataFrame, list[str], str | None]:
    """Return (member_name, contract-column frame, observed_columns, readme_head).

    Only the cleaned-table contract columns are loaded (memory-bounded on the
    ~1 GiB-decompressed hourly files); the full observed header is returned for
    the schema diff. The frame is raw (not yet cleaned).
    """
    wanted = set(RAW_COLUMNS)
    with tarfile.open(Path(path), "r") as tar:
        csv_member, readme_head = _find_members(tar)
        with _csv_stream(tar, csv_member) as header_stream:
            observed = [str(c).strip() for c in pd.read_csv(header_stream, nrows=0).columns]
        with _csv_stream(tar, csv_member) as data_stream:
            frame = pd.read_csv(data_stream, usecols=lambda c: str(c).strip() in wanted)
    frame.columns = frame.columns.str.strip()
    return csv_member.name, frame, observed, readme_head
