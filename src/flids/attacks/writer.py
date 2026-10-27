"""Guarded, chunked Parquet output for an approved Stage 1 overlay."""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Mapping, Sequence

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .assembler import OverlaySpec, iter_assembled_multi_chunks
from .config import UnapprovedConfigError, require_approved
from .fingerprint import content_fingerprint, schema_fingerprint
from .manifest import build_manifest, git_dirty, library_versions, write_manifest
from .plausibility import build_plausibility_report
from .quota import select_quota_segments
from .schemas import TABLE_NAMES


class WriterError(RuntimeError):
    """Raised when output guards or table writing fail."""


def _chunk_seconds_summary(seconds: Sequence[float]) -> dict:
    """Return min/median/p95/max of per-chunk wall-clock seconds."""
    values = sorted(float(value) for value in seconds)
    if not values:
        return {"n_chunks": 0, "min": None, "median": None, "p95": None, "max": None}

    def _quantile(points: list[float], q: float) -> float:
        if len(points) == 1:
            return points[0]
        position = q * (len(points) - 1)
        low = int(position)
        high = min(low + 1, len(points) - 1)
        frac = position - low
        return points[low] + (points[high] - points[low]) * frac

    return {
        "n_chunks": len(values),
        "min": values[0],
        "median": _quantile(values, 0.5),
        "p95": _quantile(values, 0.95),
        "max": values[-1],
    }


def _window_lsfs_to_nested(counts: Mapping[tuple, int]) -> dict:
    """Nest label x stratum x family x split window counts for the manifest."""
    nested: dict = {}
    for (label, stratum, family, split_name), count in sorted(counts.items()):
        nested.setdefault(label, {}).setdefault(stratum, {}).setdefault(family, {})[split_name] = int(count)
    return nested


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_overlay_tables(
    df: pd.DataFrame,
    overlay: OverlaySpec | Sequence[OverlaySpec],
    global_seed: int,
    split_of: Callable[[str], str],
    config: Mapping,
    *,
    config_path: str | Path,
    output_dir: str | Path,
    resolved_plan: Sequence[Mapping] | None = None,
    quota_targets: Mapping | None = None,
    conflict_priority: Sequence[str] | None = None,
    max_segments_per_chunk: int = 64,
    repo_root: str | Path | None = None,
    progress_callback: Callable[[Mapping], None] | None = None,
) -> dict:
    """Write all eight tables in chunks, refusing unapproved/dirty/overwrite.

    The caller supplies an already-loaded config mapping so this library module
    never reads YAML. The CLI owns config parsing and approval validation.
    Output directories are create-only and are never replaced or merged.
    """
    try:
        require_approved(config)
    except UnapprovedConfigError as error:
        raise WriterError(str(error)) from error
    root = Path(repo_root) if repo_root is not None else Path(config_path).resolve().parents[1]
    if git_dirty(root):
        raise WriterError("refusing dataset write from a dirty Git worktree")
    target = Path(output_dir)
    if target.exists():
        raise WriterError(f"refusing to overwrite existing output directory: {target}")
    if max_segments_per_chunk < 1:
        raise ValueError("max_segments_per_chunk must be at least one")
    overlays = (overlay,) if isinstance(overlay, OverlaySpec) else tuple(overlay)
    # Plan-order conflict resolution (D-045) keeps the given order; otherwise the
    # approved lexicographic overlay-key order.
    if conflict_priority is None:
        overlays = tuple(sorted(overlays, key=lambda item: item.overlay_key))
    priority_keys = list(conflict_priority) if conflict_priority is not None else None
    if not overlays or len({item.overlay_key for item in overlays}) != len(overlays):
        raise WriterError("at least one overlay with a unique overlay_key is required")

    # Ranked quota selection runs a global pass 1 before any directory is made
    # so a capacity shortfall fails before writing anything.
    chosen_segments = None
    quota_report = None
    if quota_targets is not None:
        fail_on_shortfall = bool((config.get("quota_mode") or {}).get("fail_on_capacity_shortfall", True))
        quota_result = select_quota_segments(
            df, overlays, global_seed, split_of, quota_targets,
            fail_on_capacity_shortfall=fail_on_shortfall,
        )
        chosen_segments = quota_result["chosen"]
        quota_report = {
            "per_cell": quota_result["per_cell"],
            "shortfall": quota_result["shortfall"],
            "fail_on_capacity_shortfall": quota_result["fail_on_capacity_shortfall"],
        }

    try:
        target.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise WriterError(f"refusing to overwrite existing output directory: {target}") from error

    writers = {}
    row_counts = {name: 0 for name in TABLE_NAMES}
    selection = {str(item.overlay_key): {
        "eligible_segments": 0, "selected_segments": 0, "chosen_segments": 0,
        "attack_rows": 0, "effective_rows": 0, "accepted_episodes": 0,
        "rejected_by_reason": {}, "attack_family": item.attack_family,
        "tier": item.tier, "tau_requested": item.tau,
    } for item in overlays}
    selection["_merged"] = {"attack_rows": 0, "effective_rows": 0, "accepted_episodes": 0, "rejected_by_reason": {}}
    # Per-overlay aircraft/window counts and per-split selection counts (S1.5).
    overlay_aircraft = {str(item.overlay_key): set() for item in overlays}
    overlay_windows = {str(item.overlay_key): 0 for item in overlays}
    per_split = {
        str(item.overlay_key): {} for item in overlays
    }  # overlay_key -> split -> {eligible, selected, chosen}
    # windows by label x stratum x family x split (family "none" for normals).
    window_lsfs: dict[tuple[str, str, str, str], int] = {}
    chunk_seconds: list[float] = []
    validator_results = {name: "passed" for name in TABLE_NAMES}
    plausibility_episodes = []
    unavailable_checks = []
    started_at = time.perf_counter()
    segments_processed = 0
    total_segments = int(df.groupby(["icao24", "segment_id"], sort=False, dropna=False).ngroups)
    total_chunks = max(1, math.ceil(total_segments / max_segments_per_chunk))
    try:
        chunks = iter(iter_assembled_multi_chunks(
            df, overlays, global_seed, split_of,
            max_segments_per_chunk=max_segments_per_chunk,
            chosen_segments=chosen_segments, priority_keys=priority_keys,
        ))
        for chunk_index in range(1, total_chunks + 1):
            if progress_callback is not None:
                progress_callback({
                    "event": "chunk_start",
                    "chunk_index": chunk_index,
                    "total_chunks": total_chunks,
                    "segments_processed": segments_processed,
                    "total_segments": total_segments,
                    "elapsed_seconds": time.perf_counter() - started_at,
                    "rows_written": dict(row_counts),
                })
            chunk_started_at = time.perf_counter()
            chunk = next(chunks)
            for name in TABLE_NAMES:
                frame = getattr(chunk, name)
                table = pa.Table.from_pandas(frame, preserve_index=False)
                path = target / f"{name}.parquet"
                if name not in writers:
                    writers[name] = pq.ParquetWriter(path, table.schema, compression="zstd")
                elif not table.schema.equals(writers[name].schema, check_metadata=False):
                    raise WriterError(f"schema changed between chunks for table {name}")
                if table.num_rows:
                    writers[name].write_table(table)
                row_counts[name] += table.num_rows

            for key, group in chunk.overlay_selections.groupby("overlay_key", sort=False):
                item = selection[str(key)]
                item["eligible_segments"] += int(group.eligible.sum())
                item["selected_segments"] += int(group.selected.sum())
                item["chosen_segments"] += int(group.chosen.sum())
                split_counts = per_split[str(key)]
                for split_name, split_group in group.groupby("split", sort=False):
                    entry = split_counts.setdefault(str(split_name), {"eligible": 0, "selected": 0, "chosen": 0})
                    entry["eligible"] += int(split_group.eligible.sum())
                    entry["selected"] += int(split_group.selected.sum())
                    entry["chosen"] += int(split_group.chosen.sum())
            # Per-overlay aircraft and window counts, via episode_id -> overlay_key.
            if not chunk.episodes.empty:
                episode_overlay = dict(zip(chunk.episodes.episode_id.tolist(), chunk.episodes.overlay_key.tolist()))
                for icao24, overlay_key in zip(chunk.episodes.icao24.tolist(), chunk.episodes.overlay_key.tolist()):
                    overlay_aircraft[str(overlay_key)].add(str(icao24))
                if not chunk.windows.empty:
                    window_overlay = chunk.windows.episode_id.map(episode_overlay)
                    for overlay_key, count in window_overlay.dropna().value_counts().items():
                        overlay_windows[str(overlay_key)] += int(count)
            # Windows by label x stratum x family x split.
            if not chunk.windows.empty:
                grouped = chunk.windows.assign(
                    _family=chunk.windows.attack_family.fillna("none")
                ).groupby(["label", "stratum", "_family", "split"], sort=False).size()
                for (label, stratum, family, split_name), count in grouped.items():
                    gkey = (str(label), str(stratum), str(family), str(split_name))
                    window_lsfs[gkey] = window_lsfs.get(gkey, 0) + int(count)
            merged = selection["_merged"]
            merged["attack_rows"] += int(chunk.attacked_rows.is_attack_row.sum())
            merged["effective_rows"] += int((chunk.attacked_rows.ramp_multiplier >= 0.5).sum())
            merged["accepted_episodes"] += int(len(chunk.episodes))
            for item in overlays:
                family = item.attack_family
                item_rows = chunk.attacked_rows[
                    (chunk.attacked_rows.attack_family == family) &
                    (chunk.attacked_rows.tier == item.tier) & chunk.attacked_rows.is_attack_row
                ]
                selection[str(item.overlay_key)]["attack_rows"] += int(len(item_rows))
                selection[str(item.overlay_key)]["effective_rows"] += int((item_rows.ramp_multiplier >= 0.5).sum())
                item_rejections = chunk.rejected_candidates[
                    chunk.rejected_candidates.overlay_key == item.overlay_key
                ]
                overlay_counts = selection[str(item.overlay_key)]
                overlay_counts["accepted_episodes"] += int((chunk.episodes.overlay_key == item.overlay_key).sum())
                if not item_rejections.empty:
                    for reason, count in item_rejections.reason.value_counts().items():
                        overlay_counts["rejected_by_reason"][str(reason)] = overlay_counts["rejected_by_reason"].get(str(reason), 0) + int(count)
            partial_report = build_plausibility_report(chunk.attacked_rows, chunk.episodes, chunk.rejected_candidates)
            plausibility_episodes.extend(partial_report["episodes"])
            unavailable_checks = partial_report["unavailable_checks"]
            if not chunk.rejected_candidates.empty:
                for reason, count in chunk.rejected_candidates.reason.value_counts().items():
                    merged["rejected_by_reason"][str(reason)] = merged["rejected_by_reason"].get(str(reason), 0) + int(count)
            segments_processed += len(chunk.segments)
            chunk_seconds.append(time.perf_counter() - chunk_started_at)
            if progress_callback is not None:
                progress_callback({
                    "event": "chunk_complete",
                    "chunk_index": chunk_index,
                    "total_chunks": total_chunks,
                    "segments_processed": segments_processed,
                    "total_segments": total_segments,
                    "chunk_seconds": time.perf_counter() - chunk_started_at,
                    "elapsed_seconds": time.perf_counter() - started_at,
                    "rows_written": dict(row_counts),
                })
    finally:
        for parquet_writer in writers.values():
            parquet_writer.close()

    # Create schema-bearing Parquet files for tables that were empty in every chunk.
    for name in TABLE_NAMES:
        path = target / f"{name}.parquet"
        if not path.exists():
            empty = pa.Table.from_pandas(getattr(next(iter_assembled_multi_chunks(df.iloc[:0], overlays, global_seed, split_of, chosen_segments=chosen_segments, priority_keys=priority_keys)), name), preserve_index=False)
            pq.write_table(empty, path, compression="zstd")

    plausibility_report = {
        "report_version": 1,
        "episode_count": len(plausibility_episodes),
        "episodes": plausibility_episodes,
        "threshold_validation": "descriptive_only_no_cutoffs_approved",
        "unavailable_checks": unavailable_checks,
    }
    (target / "plausibility_report.json").write_text(
        json.dumps(plausibility_report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    run_configuration = {
        "run_config_version": 1,
        "stage1_config": dict(config),
        "global_seed": int(global_seed),
        "overlay_specs": [asdict(item) for item in overlays],
        "library_versions": library_versions(),
    }
    (target / "config.json").write_text(
        json.dumps(run_configuration, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    input_fingerprints = {
        "cleaned_table_content": content_fingerprint(df),
        "cleaned_table_schema": schema_fingerprint(df),
    }
    manifest = build_manifest(
        config_path=config_path,
        global_seed=global_seed,
        input_fingerprints=input_fingerprints,
        dirty=False,
        git_commit=None,
    )
    total_elapsed_seconds = time.perf_counter() - started_at
    manifest.update({
        "output_directory": str(target),
        "overlay_merge_order": [item.overlay_key for item in overlays],
        "overlay_merge_scope": "lexicographic_overlay_key; at_most_one_selected_overlay_per_segment; conflicts_logged_as_overlay_conflict",
        "resolved_plan": [dict(entry) for entry in resolved_plan] if resolved_plan is not None else None,
        "selection_mode": "ranked_quota" if quota_targets is not None else "bernoulli",
        "quota": quota_report,
        "total_elapsed_seconds": total_elapsed_seconds,
        "chunk_seconds_summary": _chunk_seconds_summary(chunk_seconds),
        "window_counts_by_label_stratum_family_split": _window_lsfs_to_nested(window_lsfs),
        "overlays": {
            str(item.overlay_key): {
                **selection[str(item.overlay_key)],
                "unique_aircraft": len(overlay_aircraft[str(item.overlay_key)]),
                "window_count": overlay_windows[str(item.overlay_key)],
                "realized_tau": (selection[str(item.overlay_key)]["selected_segments"] / selection[str(item.overlay_key)]["eligible_segments"] if selection[str(item.overlay_key)]["eligible_segments"] else 0.0),
                "realized_chosen_fraction_of_eligible": (selection[str(item.overlay_key)]["chosen_segments"] / selection[str(item.overlay_key)]["eligible_segments"] if selection[str(item.overlay_key)]["eligible_segments"] else 0.0),
                "tau_by_split": {
                    split_name: {
                        "tau_requested": float(item.tau),
                        "eligible_segments": counts["eligible"],
                        "selected_segments": counts["selected"],
                        "chosen_segments": counts["chosen"],
                        "realized_tau": (counts["selected"] / counts["eligible"] if counts["eligible"] else 0.0),
                        "realized_chosen_fraction_of_eligible": (counts["chosen"] / counts["eligible"] if counts["eligible"] else 0.0),
                    }
                    for split_name, counts in sorted(per_split[str(item.overlay_key)].items())
                },
            } for item in overlays
        },
        "merged_totals": selection["_merged"],
        "tables": {
            name: {
                "row_count": row_counts[name],
                "sha256": _sha256_file(target / f"{name}.parquet"),
            }
            for name in TABLE_NAMES
        },
        "validator_results": {
            **validator_results,
            "physical_plausibility": "descriptive_report_written_no_cutoffs_approved",
        },
        "physical_plausibility_report": "plausibility_report.json",
        "unavailable_checks": unavailable_checks,
        "overlay_specs": [asdict(item) for item in overlays],
    })
    write_manifest(target / "manifest.json", manifest)
    return manifest
