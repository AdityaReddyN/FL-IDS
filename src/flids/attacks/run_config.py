"""Translate an already-loaded Stage 1 mapping into an explicit overlay spec."""
from __future__ import annotations

from .assembler import OverlaySpec
from .assembler import iter_assembled_multi_chunks
from .quota import QuotaTarget, resolve_quota_target


_FAMILIES = {
    "constant_deviation", "random_gaussian_deviation", "gradual_deviation",
    "altitude_constant_deviation", "replay_partial_field", "replay_full_field",
    "freeze_fixed_value",
}


def overlay_from_config(
    config: dict,
    attack_family: str,
    tier: str,
    *,
    tau: float | None = None,
    duration_seconds: float | None = None,
    altitude_variant: str = "baro_only",
    episodes_per_segment: int = 1,
    onset_mode: str = "linear_mix",
    tier_ratio_r: float | None = None,
    band_p95_m: dict | None = None,
    overlay_key: str | None = None,
) -> OverlaySpec:
    """Build one overlay from approved config values; does not read YAML.

    This deliberately constructs one overlay per invocation. It does not
    implement the config's quota or density-scaled sensitivity modes. When
    ``tier_ratio_r`` is given (constant_deviation only), the fixed-meter
    magnitude is replaced by the ratio-tier lookup (D-043).
    """
    ratio_mode = attack_family == "constant_deviation" and tier_ratio_r is not None
    if attack_family not in _FAMILIES:
        raise ValueError(f"unsupported attack family: {attack_family}")
    # Ratio-tier constant overlays take their magnitude from r, so the tier may
    # be a ratio-ladder rung (e.g. "floor") absent from the fixed-meter table.
    if tier not in config["tiers"]["horizontal_meters"] and not ratio_mode:
        raise ValueError(f"unsupported tier: {tier}")
    if attack_family == "altitude_constant_deviation" and altitude_variant not in {"baro_only", "baro_plus_geo"}:
        raise ValueError(f"unsupported altitude variant: {altitude_variant}")
    taus = config["prevalence"]["tau_sweep"]
    requested_tau = float(taus[0] if tau is None else tau)
    episodes = config["episodes"]
    duration = duration_seconds
    if duration is None:
        if attack_family == "freeze_fixed_value":
            duration = episodes["freeze_duration_tiers_seconds"][tier]
        else:
            duration = episodes["nominal_duration_seconds"]
    tiers = config["tiers"]
    magnitude = sigma = shift = None
    gaussian = config["attacks"]["gaussian"]
    kappa = float(gaussian["eq12_noise_kappa_by_tier"].get(tier, 0.0))
    if attack_family == "gradual_deviation" or (attack_family == "constant_deviation" and not ratio_mode):
        magnitude = float(tiers["horizontal_meters"][tier])
    # ratio_mode leaves magnitude None (per-episode ratio-tier lookup in the assembler).
    if attack_family == "random_gaussian_deviation":
        sigma = float(gaussian["deviation_sigma_meters_by_tier"][tier])
    if attack_family == "altitude_constant_deviation":
        shift = float(tiers["altitude_residual_calibration_meters"]["shared_shift_both_variants"][tier])
    subtype = {
        "constant_deviation": "constant",
        "random_gaussian_deviation": "gaussian",
        "gradual_deviation": "gradual",
        "altitude_constant_deviation": altitude_variant,
        "replay_partial_field": "partial",
        "replay_full_field": "full",
        "freeze_fixed_value": "freeze",
    }[attack_family]
    replay = config["eligibility"]["replay"]
    glitch = config["eligibility"].get("geoaltitude_glitch_screen", {}).get("train_only_q999_threshold_meters")
    return OverlaySpec(
        attack_family=attack_family,
        tier=tier,
        subtype=subtype,
        altitude_variant=altitude_variant if attack_family == "altitude_constant_deviation" else None,
        duration_seconds=float(duration),
        ramp_rows=int(episodes["onset"]["default_steps"]),
        magnitude_m=magnitude,
        sigma_m=sigma,
        kappa=kappa,
        per_step_sigma_m=float(gaussian["per_step_noise_sigma_meters"]),
        shift_m=shift,
        replay_delay_s=float(replay["paper_grounded_delay_seconds"]),
        replay_tolerance_s=float(replay["timestamp_tolerance_seconds"]),
        tau=requested_tau,
        onset_mode=onset_mode,
        episodes_per_segment=episodes_per_segment,
        tier_ratio_r=tier_ratio_r if attack_family == "constant_deviation" else None,
        band_p95_m=dict(band_p95_m) if (band_p95_m is not None and attack_family == "constant_deviation" and tier_ratio_r is not None) else None,
        overlay_key=overlay_key,
        dataset_mode=config["region"]["primary_dataset_mode"],
        geoaltitude_glitch_threshold_m=float(glitch) if attack_family == "altitude_constant_deviation" and altitude_variant == "baro_plus_geo" and glitch is not None else None,
        min_gap_seconds=float(episodes["minimum_inter_episode_gap_seconds"]),
    )


def plan_mode(plan: dict) -> str:
    """Return ``"quota"`` or ``"bernoulli"`` for a run plan; reject a mix.

    A plan is homogeneous: every overlay uses ``tau`` (Bernoulli realistic
    prevalence) or every overlay uses ``quota_target`` (ranked quota). Mixing
    the two selection modes in one run is not supported.
    """
    has_tau = any(entry.get("tau") is not None for entry in plan["overlays"])
    has_quota = any(entry.get("quota_target") is not None for entry in plan["overlays"])
    if has_tau and has_quota:
        raise ValueError("a run plan must be all-tau (Bernoulli) or all-quota, not mixed")
    return "quota" if has_quota else "bernoulli"


def _overlay_from_entry(config: dict, entry: dict, band_p95_m: dict | None = None) -> OverlaySpec:
    # Quota overlays carry tau=0.0: selection is overridden by the ranked quota
    # chosen set, so the Bernoulli probability is unused (D-038).
    tau = float(entry["tau"]) if entry.get("tau") is not None else 0.0
    return overlay_from_config(
        config,
        entry["family"],
        entry["tier"],
        tau=tau,
        duration_seconds=float(entry["duration_seconds"]),
        altitude_variant=entry.get("altitude_variant", "baro_only"),
        episodes_per_segment=int(entry.get("episodes_per_segment", 1)),
        onset_mode=entry.get("onset_mode", "linear_mix"),
        tier_ratio_r=entry.get("tier_ratio_r"),
        band_p95_m=band_p95_m,
        overlay_key=entry.get("overlay_key"),
    )


def overlays_from_plan(config: dict, plan: dict) -> tuple[OverlaySpec, ...]:
    """Build the overlays for one run from an already-validated run plan.

    Works for both selection modes. For a quota plan the overlays carry
    ``tau=0.0`` (unused); the per-cell targets come from
    :func:`quota_targets_from_plan`. Ratio-tier overlays (constant_deviation with
    ``tier_ratio_r``) read the plan's ``band_p95_m`` table (D-043).
    """
    band_p95_m = plan.get("band_p95_m")
    return tuple(_overlay_from_entry(config, entry, band_p95_m) for entry in plan["overlays"])


def quota_targets_from_plan(config: dict, plan: dict) -> dict[str, QuotaTarget] | None:
    """Return per-overlay quota targets, or ``None`` for a Bernoulli plan."""
    if plan_mode(plan) != "quota":
        return None
    targets: dict[str, QuotaTarget] = {}
    for entry in plan["overlays"]:
        overlay = _overlay_from_entry(config, entry)
        targets[overlay.overlay_key] = resolve_quota_target(config, entry)
    return targets


def dry_run_summary(
    df,
    overlay: OverlaySpec | tuple[OverlaySpec, ...] | list[OverlaySpec],
    global_seed: int,
    split_of,
    *,
    max_segments_per_chunk: int = 64,
) -> dict:
    """Count the in-memory assembly without creating files or directories."""
    overlays = (overlay,) if isinstance(overlay, OverlaySpec) else tuple(overlay)
    result = {
        "input_rows": int(len(df)),
        "eligible_segments_by_overlay": {},
        "selected_segments_by_overlay": {},
        "chosen_segments_by_overlay": {},
        "accepted_episodes": 0,
        "rejected_by_reason": {},
        "rows_by_table": {},
    }
    for chunk in iter_assembled_multi_chunks(
        df, overlays, global_seed, split_of,
        max_segments_per_chunk=max_segments_per_chunk,
    ):
        result["accepted_episodes"] += len(chunk.episodes)
        for key, group in chunk.overlay_selections.groupby("overlay_key", sort=False):
            result["eligible_segments_by_overlay"][str(key)] = result["eligible_segments_by_overlay"].get(str(key), 0) + int(group.eligible.sum())
            result["selected_segments_by_overlay"][str(key)] = result["selected_segments_by_overlay"].get(str(key), 0) + int(group.selected.sum())
            result["chosen_segments_by_overlay"][str(key)] = result["chosen_segments_by_overlay"].get(str(key), 0) + int(group.chosen.sum())
        for name in ("attacked_rows", "step_labels", "episodes", "rejected_candidates", "modified_row_provenance", "windows", "segments", "overlay_selections"):
            result["rows_by_table"][name] = result["rows_by_table"].get(name, 0) + len(getattr(chunk, name))
        if not chunk.rejected_candidates.empty:
            for reason, count in chunk.rejected_candidates.reason.value_counts().items():
                key = str(reason)
                result["rejected_by_reason"][key] = result["rejected_by_reason"].get(key, 0) + int(count)
    result["eligible_segments"] = sum(result["eligible_segments_by_overlay"].values())
    result["selected_segments"] = sum(result["selected_segments_by_overlay"].values())
    return result
