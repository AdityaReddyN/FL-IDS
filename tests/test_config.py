import pytest
import yaml

from flids.attacks.config import (
    REQUIRED_TOP_LEVEL_KEYS,
    ConfigError,
    UnapprovedConfigError,
    load_approved_config,
    load_config,
    require_approved,
    validate_config,
)


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
