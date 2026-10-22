"""Deterministic, order-independent random streams for attack generation.

Segment streams are derived from ``SHA-256(f"{global_seed}|{icao24}|{segment_id}")``.
Episode streams reuse the segment entropy with ``spawn_key=(episode_index,)``, so
episode ``k`` never depends on how many other episodes exist or on call order.
Python's ``hash()`` and NumPy's global RNG are never used.
"""

from __future__ import annotations

import hashlib
from numbers import Integral

import numpy as np


def _segment_entropy(global_seed: int, icao24: str, segment_id: int) -> int:
    segment_id = int(segment_id)
    key = f"{global_seed}|{icao24}|{segment_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest(), "big")


def _parameter_entropy(global_seed: int, icao24: str, segment_id: int) -> int:
    key = f"{global_seed}|{icao24}|{int(segment_id)}|params".encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest(), "big")


def _placement_entropy(global_seed: int, icao24: str, segment_id: int) -> int:
    key = f"{global_seed}|{icao24}|{int(segment_id)}|placement".encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest(), "big")


def segment_seed_sequence(
    global_seed: int, icao24: str, segment_id: int
) -> np.random.SeedSequence:
    """Return the reproducible seed sequence for one aircraft segment."""
    return np.random.SeedSequence(_segment_entropy(global_seed, icao24, segment_id))


def segment_rng(global_seed: int, icao24: str, segment_id: int) -> np.random.Generator:
    """Return a fresh generator for one aircraft segment."""
    return np.random.default_rng(
        segment_seed_sequence(global_seed, icao24, segment_id)
    )


def episode_seed_sequence(
    global_seed: int,
    icao24: str,
    segment_id: int,
    episode_index: int,
) -> np.random.SeedSequence:
    """Return the seed sequence for episode ``episode_index`` of a segment."""
    if not isinstance(episode_index, Integral) or isinstance(episode_index, bool):
        raise TypeError("episode_index must be a non-negative integer")
    if episode_index < 0:
        raise ValueError("episode_index must be non-negative")

    segment_sequence = segment_seed_sequence(global_seed, icao24, segment_id)
    return np.random.SeedSequence(
        entropy=segment_sequence.entropy,
        spawn_key=(int(episode_index),),
    )


def episode_rng(
    global_seed: int,
    icao24: str,
    segment_id: int,
    episode_index: int,
) -> np.random.Generator:
    """Return a fresh generator for one episode, independent of other episodes."""
    return np.random.default_rng(
        episode_seed_sequence(global_seed, icao24, segment_id, episode_index)
    )


def parameter_seed_sequence(
    global_seed: int, icao24: str, segment_id: int, episode_index: int
) -> np.random.SeedSequence:
    """Return an episode-indexed stream reserved for signs and bearings."""
    if not isinstance(episode_index, Integral) or isinstance(episode_index, bool):
        raise TypeError("episode_index must be a non-negative integer")
    if episode_index < 0:
        raise ValueError("episode_index must be non-negative")
    return np.random.SeedSequence(
        entropy=_parameter_entropy(global_seed, icao24, segment_id),
        spawn_key=(int(episode_index),),
    )


def parameter_rng(
    global_seed: int, icao24: str, segment_id: int, episode_index: int
) -> np.random.Generator:
    """Return the independent parameter stream for one episode."""
    return np.random.default_rng(
        parameter_seed_sequence(global_seed, icao24, segment_id, episode_index)
    )


def placement_rng(global_seed: int, icao24: str, segment_id: int, episode_index: int) -> np.random.Generator:
    """Return the independent placement stream for one episode request."""
    if not isinstance(episode_index, Integral) or isinstance(episode_index, bool):
        raise TypeError("episode_index must be a non-negative integer")
    if episode_index < 0:
        raise ValueError("episode_index must be non-negative")
    return np.random.default_rng(np.random.SeedSequence(
        entropy=_placement_entropy(global_seed, icao24, segment_id), spawn_key=(int(episode_index),)
    ))
