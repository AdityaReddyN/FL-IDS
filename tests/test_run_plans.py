"""The D-039 A/B/C run plans load, validate, and build overlays (S7a)."""

from pathlib import Path

import pytest

from flids.attacks.config import load_approved_config, load_run_plan
from flids.attacks.run_config import overlays_from_plan, plan_mode, quota_targets_from_plan

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "attack_v3_stage1.yaml"
PLANS = {
    "A": ROOT / "configs" / "run_plans" / "plan_A_per_cell_eval.yaml",
    "B": ROOT / "configs" / "run_plans" / "plan_B_mixed_realistic.yaml",
    "C": ROOT / "configs" / "run_plans" / "plan_C_trackB_training.yaml",
}


@pytest.fixture(scope="module")
def config():
    return load_approved_config(CONFIG)


@pytest.mark.parametrize("kind", ["A", "B", "C"])
def test_plan_loads_validates_and_builds(config, kind):
    plan = load_run_plan(PLANS[kind])  # validates structure (incl. overlay_key uniqueness)
    overlays = overlays_from_plan(config, plan)
    assert overlays
    # Every constant_deviation overlay uses a ratio tier and the plan's p95 table.
    const = [o for o in overlays if o.attack_family == "constant_deviation"]
    assert const
    for o in const:
        assert o.tier_ratio_r is not None and o.magnitude_m is None
        assert o.band_p95_m["100_200"] == 1653.6
    assert len({o.overlay_key for o in overlays}) == len(overlays)


def test_plan_A_is_the_joint_quota_run_with_floor_rung(config):
    overlays = overlays_from_plan(config, load_run_plan(PLANS["A"]))
    assert len(overlays) == 25
    ratios = {o.tier_ratio_r for o in overlays if o.attack_family == "constant_deviation"}
    assert {0.5, 0.9, 1.0, 1.1, 2.0} <= ratios  # floor..gross ladder present


def test_plan_A_is_quota_and_BC_are_bernoulli(config):
    assert plan_mode(load_run_plan(PLANS["A"])) == "quota"
    assert quota_targets_from_plan(config, load_run_plan(PLANS["A"])) is not None
    for kind in ("B", "C"):
        assert plan_mode(load_run_plan(PLANS[kind])) == "bernoulli"


def test_plan_gradual_uses_long_duration(config):
    # Gradual at 120 s would be rejected (< 5 effective rows); plans use 900 s.
    for kind in ("B", "C"):
        overlays = overlays_from_plan(config, load_run_plan(PLANS[kind]))
        gradual = [o for o in overlays if o.attack_family == "gradual_deviation"]
        assert gradual and gradual[0].duration_seconds == 900
