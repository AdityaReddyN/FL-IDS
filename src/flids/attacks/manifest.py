"""Skeleton manifest for a Stage 1 attack-generation run.

The manifest records the config file hash, git commit, library versions, input
fingerprints, and the global seed. Attack counts and region/cell statistics are
added by later stages.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import pyarrow
import yaml

MANIFEST_VERSION = 1
_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]


def config_hash(config_path: str | Path) -> str:
    """Return the SHA-256 hex digest of the config file bytes."""
    return hashlib.sha256(Path(config_path).read_bytes()).hexdigest()


def git_commit_hash(repo_root: str | Path | None = None) -> str:
    """Return the current commit hash, or ``unknown`` outside a git checkout."""
    root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def git_dirty(repo_root: str | Path | None = None) -> bool:
    """Return True when the work tree has tracked or untracked changes."""
    root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return bool(result.stdout.strip())


def library_versions() -> dict[str, str]:
    """Return versions of the libraries that affect generated artifacts."""
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "pyarrow": pyarrow.__version__,
        "pyyaml": yaml.__version__,
    }


def build_manifest(
    config_path: str | Path,
    global_seed: int,
    input_fingerprints: Mapping[str, str],
    git_commit: str | None = None,
    versions: Mapping[str, str] | None = None,
    dirty: bool | None = None,
) -> dict[str, Any]:
    """Build the manifest dictionary for one attack-generation run."""
    return {
        "manifest_version": MANIFEST_VERSION,
        "config_sha256": config_hash(config_path),
        "git_commit": git_commit if git_commit is not None else git_commit_hash(),
        "git_dirty": dirty if dirty is not None else git_dirty(),
        "library_versions": dict(
            versions if versions is not None else library_versions()
        ),
        "input_fingerprints": dict(input_fingerprints),
        "global_seed": int(global_seed),
    }


def write_manifest(path: str | Path, manifest: Mapping[str, Any]) -> None:
    """Write a manifest as stable, readable JSON."""
    target = Path(path)
    target.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
