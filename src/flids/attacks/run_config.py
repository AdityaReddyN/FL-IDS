"""Translate an already-loaded Stage 1 mapping into an explicit overlay spec."""
from __future__ import annotations

from .assembler import OverlaySpec
from .assembler import iter_assembled_multi_chunks


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
) -> OverlaySpec:
    """Build one overlay from approved config values; does not read YAML.

    This deliberately constructs one overlay per invocation. It does not
    implement the config's quota or density-scaled sensitivity modes.
    """
    if attack_family not in _FAMILIES:
        raise ValueError(f"unsupported attack family: {attack_family}")
    if tier not in config["tiers"]["horizontal_meters"]:
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
    if attack_family in {"constant_deviation", "gradual_deviation"}:
        magnitude = float(tiers["horizontal_meters"][tier])
    elif attack_family == "random_gaussian_deviation":
        sigma = float(gaussian["deviation_sigma_meters_by_tier"][tier])
    elif attack_family == "altitude_constant_deviation":
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
        episodes_per_segment=episodes_per_segment,
        dataset_mode=config["region"]["primary_dataset_mode"],
        geoaltitude_glitch_threshold_m=float(glitch) if attack_family == "altitude_constant_deviation" and altitude_variant == "baro_plus_geo" and glitch is not None else None,
        min_gap_seconds=float(episodes["minimum_inter_episode_gap_seconds"]),
    )


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
