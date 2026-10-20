import hashlib
import json
import re
from pathlib import Path

from flids.attacks.manifest import (
    build_manifest,
    config_hash,
    git_commit_hash,
    library_versions,
    write_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


def test_config_hash_is_sha256_of_file_bytes(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_bytes(b"global_seed: 42\nstatus: approved\n")
    assert config_hash(path) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_build_manifest_records_required_fields(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_bytes(b"global_seed: 42\n")
    manifest = build_manifest(
        config_path=path,
        global_seed=42,
        input_fingerprints={
            "cleaned_table_content": "abc123",
            "cleaned_table_schema": "def456",
        },
        git_commit="deadbeef",
        versions={"numpy": "test"},
    )
    assert manifest["manifest_version"] == 1
    assert manifest["global_seed"] == 42
    assert manifest["config_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert manifest["git_commit"] == "deadbeef"
    assert manifest["library_versions"] == {"numpy": "test"}
    assert manifest["input_fingerprints"]["cleaned_table_content"] == "abc123"


def test_write_manifest_round_trips(tmp_path) -> None:
    target = tmp_path / "manifest.json"
    manifest = {"b": 2, "a": 1}
    write_manifest(target, manifest)
    assert json.loads(target.read_text(encoding="utf-8")) == manifest


def test_library_versions_includes_pinned_stack() -> None:
    versions = library_versions()
    for package in ("python", "numpy", "pandas", "pyarrow", "pyyaml"):
        assert versions[package]


def test_git_commit_hash_reads_current_repository() -> None:
    assert re.fullmatch(r"[0-9a-f]{40}", git_commit_hash(ROOT))
