"""Guarded, chunked Parquet output for an approved Stage 1 overlay."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Mapping

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .assembler import OverlaySpec, iter_assembled_chunks
from .config import UnapprovedConfigError, require_approved
from .fingerprint import content_fingerprint, schema_fingerprint
from .manifest import build_manifest, git_dirty, write_manifest
from .plausibility import build_plausibility_report
from .schemas import TABLE_NAMES


class WriterError(RuntimeError):
    """Raised when output guards or table writing fail."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_overlay_tables(
    df: pd.DataFrame,
    overlay: OverlaySpec,
    global_seed: int,
    split_of: Callable[[str], str],
    config: Mapping,
    *,
    config_path: str | Path,
    output_dir: str | Path,
    max_segments_per_chunk: int = 64,
    repo_root: str | Path | None = None,
) -> dict:
    """Write all seven tables in chunks, refusing unapproved/dirty/overwrite.

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

    try:
        target.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise WriterError(f"refusing to overwrite existing output directory: {target}") from error

    writers = {}
    row_counts = {name: 0 for name in TABLE_NAMES}
    selection = {
        "eligible_segments": 0,
        "selected_segments": 0,
        "realized_eta": None,
        "attack_rows": 0,
        "effective_rows": 0,
        "accepted_episodes": 0,
        "rejected_by_reason": {},
    }
    validator_results = {name: "passed" for name in TABLE_NAMES}
    plausibility_episodes = []
    unavailable_checks = []
    try:
        for chunk in iter_assembled_chunks(df, overlay, global_seed, split_of, max_segments_per_chunk=max_segments_per_chunk):
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

            selection["eligible_segments"] += int(chunk.segments.eligible.sum())
            selection["selected_segments"] += int(chunk.segments.selected.sum())
            selection["attack_rows"] += int(chunk.attacked_rows.is_attack_row.sum())
            selection["effective_rows"] += int((chunk.attacked_rows.ramp_multiplier >= 0.5).sum())
            selection["accepted_episodes"] += int(len(chunk.episodes))
            partial_report = build_plausibility_report(chunk.attacked_rows, chunk.episodes, chunk.rejected_candidates)
            plausibility_episodes.extend(partial_report["episodes"])
            unavailable_checks = partial_report["unavailable_checks"]
            if not chunk.rejected_candidates.empty:
                for reason, count in chunk.rejected_candidates.reason.value_counts().items():
                    selection["rejected_by_reason"][str(reason)] = selection["rejected_by_reason"].get(str(reason), 0) + int(count)
    finally:
        for parquet_writer in writers.values():
            parquet_writer.close()

    # Create schema-bearing Parquet files for tables that were empty in every chunk.
    for name in TABLE_NAMES:
        path = target / f"{name}.parquet"
        if not path.exists():
            empty = pa.Table.from_pandas(getattr(next(iter_assembled_chunks(df.iloc[:0], overlay, global_seed, split_of)), name), preserve_index=False)
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
    manifest.update({
        "output_directory": str(target),
        "overlay_merge_order": [overlay.overlay_key],
        "overlay_merge_scope": "single_overlay_per_run; cross_overlay_conflicts_not_resolved",
        "overlays": {
            str(overlay.overlay_key): {
                **selection,
                "realized_eta": selection["selected_segments"] / selection["eligible_segments"] if selection["eligible_segments"] else 0.0,
                "attack_family": overlay.attack_family,
                "tier": overlay.tier,
                "tau_requested": overlay.tau,
            }
        },
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
        "overlay_spec": asdict(overlay),
    })
    write_manifest(target / "manifest.json", manifest)
    return manifest
