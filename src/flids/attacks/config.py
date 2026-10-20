"""Load and validate the Stage 1 attack configuration.

The real YAML stays ``status: proposed_unapproved`` until the human approves it.
:func:`require_approved` is the hard gate for any dataset-generation entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

APPROVED_STATUS = "approved"

REQUIRED_TOP_LEVEL_KEYS: tuple[str, ...] = (
    "version",
    "status",
    "global_seed",
    "injection_realization_global_seeds",
    "input",
    "output",
    "splits",
    "region",
    "eligibility",
    "window_labelling",
    "reporting_strata_gates",
    "episodes",
    "attacks",
    "tiers",
    "prevalence",
    "quota_mode",
    "evaluation",
    "track_a",
    "track_b",
    "phase2_safeguards",
    "release_gate",
)


class ConfigError(ValueError):
    """Raised when an attack configuration is malformed."""


class UnapprovedConfigError(ConfigError):
    """Raised when dataset generation is attempted with an unapproved config."""


def load_config(path: str | Path) -> dict[str, Any]:
    """Read a YAML config file into a dictionary."""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ConfigError(f"{config_path} must contain a YAML mapping")
    return data


def validate_config(
    config: Mapping[str, Any],
    required_keys: Iterable[str] = REQUIRED_TOP_LEVEL_KEYS,
) -> None:
    """Raise :class:`ConfigError` if required top-level keys are missing."""
    if not isinstance(config, Mapping):
        raise ConfigError("config must be a mapping")
    missing = [key for key in required_keys if key not in config]
    if missing:
        raise ConfigError(
            "missing required top-level key(s): " + ", ".join(sorted(missing))
        )


def require_approved(config: Mapping[str, Any]) -> None:
    """Refuse to continue unless the config status is exactly ``approved``."""
    status = config.get("status")
    if status != APPROVED_STATUS:
        raise UnapprovedConfigError(
            f"config status is {status!r}; dataset generation requires "
            f"{APPROVED_STATUS!r}"
        )


def load_approved_config(
    path: str | Path,
    required_keys: Iterable[str] = REQUIRED_TOP_LEVEL_KEYS,
) -> dict[str, Any]:
    """Load, validate, and approval-check a config in one call."""
    config = load_config(path)
    validate_config(config, required_keys)
    require_approved(config)
    return config
