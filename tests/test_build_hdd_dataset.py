"""End-to-end tests for the HDD cleaner and clean-source validator (S5).

Build a mini dataset from synthetic ``.csv.gz``-in-``.tar`` fixtures laid out
like the real archives, then assert the cleaned-table contract, segment
splitting, the global split, 10 s cadence, and that the validator passes.
"""

import gzip
import importlib.util
import io
import tarfile
from pathlib import Path

import pandas as pd
import pytest

from flids.data.clean import CLEAN_COLUMNS, clean_frame

ROOT = Path(__file__).resolve().parents[1]


def _load(script: str):
    spec = importlib.util.spec_from_file_location(script, ROOT / "scripts" / f"{script}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_archive(dir_path: Path, name: str, csv_text: str) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    gz = gzip.compress(csv_text.encode("utf-8"))
    path = dir_path / name
    inner = name.replace(".tar", ".gz")
    with tarfile.open(path, "w") as tar:
        info = tarfile.TarInfo(name=inner)
        info.size = len(gz)
        tar.addfile(info, io.BytesIO(gz))
        readme = b"OpenSky Data Sample"
        rinfo = tarfile.TarInfo(name="README.txt")
        rinfo.size = len(readme)
        tar.addfile(rinfo, io.BytesIO(readme))


HEADER = "time,icao24,lat,lon,velocity,heading,vertrate,callsign,onground,baroaltitude,geoaltitude,lastcontact\n"


def _rows(icao: str, base: int, n: int, step: int = 10) -> str:
    out = []
    for i in range(n):
        t = base + i * step
        out.append(f"{t},{icao},{10.0 + i*0.01},{20.0 + i*0.01},100.0,90.0,0.0,ABC,False,3000,3010,{t}")
    return "\n".join(out) + "\n"


def _make_hdd_tree(tmp_path: Path) -> Path:
    root = tmp_path / "hdd"
    # date 1, hour 0: aircraft aaa (with a >30s gap mid-track) and bbb
    csv1 = HEADER + _rows("aaa", 0, 4) + _rows("aaa", 1000, 3) + _rows("bbb", 0, 5)
    _write_archive(root / ".2019-11-18" / "00", "states_2019-11-18-00.csv.tar", csv1)
    # date 2 (a week later): aircraft aaa again -> must be a new segment
    csv2 = HEADER + _rows("aaa", 604800, 4) + _rows("ccc", 0, 6)
    _write_archive(root / ".2019-11-25" / "00", "states_2019-11-25-00.csv.tar", csv2)
    return root


def test_clean_frame_conventions_and_segment_split():
    csv = HEADER + _rows("aaa", 0, 3) + _rows("aaa", 1000, 2)
    raw = pd.read_csv(io.StringIO(csv))
    clean = clean_frame(raw)
    assert list(clean.columns) == list(CLEAN_COLUMNS)
    # The >30 s jump (30 -> 1000) starts a second segment for aaa.
    assert clean["segment_id"].nunique() == 2
    assert str(clean["time"].dtype) == "int64"
    assert str(clean["segment_id"].dtype) == "int32"


def test_build_hdd_dataset_end_to_end(tmp_path, monkeypatch):
    builder = _load("build_hdd_dataset")
    root = _make_hdd_tree(tmp_path)
    out = tmp_path / "hdd_clean_v1"
    # Keep the git-state helper from refusing (tmp tree is not a repo anyway).
    manifest = builder.build(root, out, buckets=4, segment_gap_seconds=30.0,
                             seed=42, velocity_glitch_mps=400.0, keep_buckets=False)

    assert manifest["aircraft"] == 3  # aaa, bbb, ccc
    assert manifest["rows"] == 4 + 3 + 5 + 4 + 6  # 22 rows
    # aaa: three segments (gap within date 1, plus the week gap to date 2);
    # bbb: 1; ccc: 1 -> 5 segments total.
    assert manifest["segments"] == 5
    assert (out / "split_aircraft.json").exists()
    assert sum(manifest["split_counts"].values()) == 3

    # Every part matches the cleaned-table contract.
    parts = sorted(out.glob("part_*.parquet"))
    assert parts
    for part in parts:
        assert list(pd.read_parquet(part).columns) == list(CLEAN_COLUMNS)

    validator = _load("validate_clean_source")
    report = validator.validate(out, reference_parquet=None)
    assert report["passed"], report["checks"]
    assert report["checks"]["within_segment_cadence_10s"]["modal_dt_seconds"] == 10


def test_build_refuses_existing_output(tmp_path):
    builder = _load("build_hdd_dataset")
    root = _make_hdd_tree(tmp_path)
    out = tmp_path / "existing"
    out.mkdir()
    with pytest.raises(SystemExit, match="overwrite"):
        builder.build(root, out, buckets=4, segment_gap_seconds=30.0,
                      seed=42, velocity_glitch_mps=400.0, keep_buckets=False)
