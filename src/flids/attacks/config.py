"""Load and validate the Stage 1 attack configuration.

Dataset-generation entry points must call :func:`require_approved`; the checked
in config status records the latest human decision, not an agent decision.
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


PLAN_FAMILIES: tuple[str, ...] = (
    "constant_deviation", "random_gaussian_deviation", "gradual_deviation",
    "altitude_constant_deviation", "replay_partial_field", "replay_full_field",
    "freeze_fixed_value",
)
PLAN_TIERS: tuple[str, ...] = (
    "subtle", "moderate", "blatant", "gross_positive_control",
)
PLAN_ONSET_MODES: tuple[str, ...] = ("linear_mix", "abrupt")
PLAN_ALTITUDE_VARIANTS: tuple[str, ...] = ("baro_only", "baro_plus_geo")


class ConfigError(ValueError):
    """Raised when an attack configuration is malformed."""


class PlanError(ConfigError):
    """Raised when a run plan file is malformed."""


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


def validate_run_plan(plan: Mapping[str, Any]) -> None:
    """Validate a run-plan mapping (overlay list for one generation run).

    A plan lists the overlays for one run: each overlay names a ``family``,
    ``tier`` and ``duration_seconds``, with optional ``onset_mode``,
    ``altitude_variant`` and ``episodes_per_segment``, and exactly one of
    ``tau`` (Bernoulli prevalence mode) or ``quota_target`` (ranked quota mode,
    implemented in Stage S2). The format accepts both; building a quota overlay
    is deferred to S2.
    """
    if not isinstance(plan, Mapping):
        raise PlanError("run plan must be a mapping")
    if plan.get("plan_version") != 1:
        raise PlanError("run plan requires plan_version: 1")
    overlays = plan.get("overlays")
    if not isinstance(overlays, list) or not overlays:
        raise PlanError("run plan requires a non-empty 'overlays' list")
    for index, entry in enumerate(overlays):
        where = f"overlays[{index}]"
        if not isinstance(entry, Mapping):
            raise PlanError(f"{where} must be a mapping")
        family = entry.get("family")
        if family not in PLAN_FAMILIES:
            raise PlanError(f"{where}.family must be one of {PLAN_FAMILIES}; got {family!r}")
        if entry.get("tier") not in PLAN_TIERS:
            raise PlanError(f"{where}.tier must be one of {PLAN_TIERS}; got {entry.get('tier')!r}")
        if "duration_seconds" not in entry:
            raise PlanError(f"{where} requires duration_seconds")
        onset = entry.get("onset_mode", "linear_mix")
        if onset not in PLAN_ONSET_MODES:
            raise PlanError(f"{where}.onset_mode must be one of {PLAN_ONSET_MODES}; got {onset!r}")
        variant = entry.get("altitude_variant", "baro_only")
        if variant not in PLAN_ALTITUDE_VARIANTS:
            raise PlanError(f"{where}.altitude_variant must be one of {PLAN_ALTITUDE_VARIANTS}; got {variant!r}")
        has_tau = entry.get("tau") is not None
        has_quota = entry.get("quota_target") is not None
        if has_tau == has_quota:
            raise PlanError(f"{where} must set exactly one of 'tau' or 'quota_target'")


def load_run_plan(path: str | Path) -> dict[str, Any]:
    """Read and validate a run-plan YAML file."""
    plan_path = Path(path)
    with plan_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise PlanError(f"{plan_path} must contain a YAML mapping")
    validate_run_plan(data)
    return data
