import pytest
import yaml

from flids.attacks.config import (
    REQUIRED_TOP_LEVEL_KEYS,
    ConfigError,
    PlanError,
    UnapprovedConfigError,
    load_approved_config,
    load_config,
    load_run_plan,
    require_approved,
    validate_config,
    validate_run_plan,
)


def good_plan() -> dict:
    return {
        "plan_version": 1,
        "name": "example",
        "overlays": [
            {"family": "constant_deviation", "tier": "moderate", "duration_seconds": 120, "tau": 0.005},
            {"family": "gradual_deviation", "tier": "moderate", "duration_seconds": 900,
             "onset_mode": "abrupt", "tau": 0.01},
            {"family": "altitude_constant_deviation", "tier": "moderate", "duration_seconds": 120,
             "altitude_variant": "baro_plus_geo", "quota_target": {"episodes": 50, "unique_aircraft": 40}},
        ],
    }


def test_validate_run_plan_accepts_tau_and_quota_entries() -> None:
    validate_run_plan(good_plan())


def test_validate_run_plan_rejects_bad_plans() -> None:
    with pytest.raises(PlanError, match="plan_version"):
        validate_run_plan({"overlays": [{"family": "constant_deviation", "tier": "moderate", "duration_seconds": 120, "tau": 0.005}]})
    with pytest.raises(PlanError, match="overlays"):
        validate_run_plan({"plan_version": 1, "overlays": []})
    with pytest.raises(PlanError, match="family"):
        validate_run_plan({"plan_version": 1, "overlays": [{"family": "ghost", "tier": "moderate", "duration_seconds": 120, "tau": 0.005}]})
    with pytest.raises(PlanError, match="exactly one"):
        validate_run_plan({"plan_version": 1, "overlays": [{"family": "constant_deviation", "tier": "moderate", "duration_seconds": 120}]})
    with pytest.raises(PlanError, match="exactly one"):
        validate_run_plan({"plan_version": 1, "overlays": [{"family": "constant_deviation", "tier": "moderate", "duration_seconds": 120, "tau": 0.005, "quota_target": {"episodes": 1}}]})


def test_load_run_plan_round_trips(tmp_path) -> None:
    path = tmp_path / "plan.yaml"
    path.write_text(yaml.safe_dump(good_plan()), encoding="utf-8")
    loaded = load_run_plan(path)
    assert loaded["plan_version"] == 1
    assert len(loaded["overlays"]) == 3


def minimal_config(status: str = "approved") -> dict:
    config = {key: {} for key in REQUIRED_TOP_LEVEL_KEYS}
    config.update({"version": "test_v1", "status": status, "global_seed": 7})
    return config


def write_yaml(tmp_path, config: dict):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_load_config_reads_yaml(tmp_path) -> None:
    path = write_yaml(tmp_path, minimal_config())
    config = load_config(path)
    assert config["global_seed"] == 7
    assert config["status"] == "approved"


def test_validate_config_rejects_missing_key() -> None:
    config = minimal_config()
    del config["episodes"]
    with pytest.raises(ConfigError, match="episodes"):
        validate_config(config)


def test_validate_config_rejects_non_mapping() -> None:
    with pytest.raises(ConfigError, match="mapping"):
        validate_config(["not", "a", "mapping"])


def test_require_approved_passes_for_approved() -> None:
    require_approved(minimal_config(status="approved"))


def test_require_approved_refuses_draft_status() -> None:
    with pytest.raises(UnapprovedConfigError, match="proposed_unapproved"):
        require_approved(minimal_config(status="proposed_unapproved"))


def test_load_approved_config_refuses_draft(tmp_path) -> None:
    path = write_yaml(tmp_path, minimal_config(status="proposed_unapproved"))
    with pytest.raises(UnapprovedConfigError):
        load_approved_config(path)


def test_load_approved_config_accepts_approved(tmp_path) -> None:
    path = write_yaml(tmp_path, minimal_config(status="approved"))
    assert load_approved_config(path)["global_seed"] == 7
