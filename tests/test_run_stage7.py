"""Dry-run smoke test for the Stage 7 driver (S7)."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("run_stage7", ROOT / "scripts" / "run_stage7.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dry_run_lists_phases_and_writes_nothing(monkeypatch, capsys):
    module = _load()
    monkeypatch.setattr(sys, "argv", ["run_stage7.py", "--dry-run"])
    assert module.main() == 0
    out = capsys.readouterr().out
    for phase in ("preflight", "capacity", "benchmark", "pilot", "full_A", "B", "C"):
        assert phase in out
    assert "Generation gate: CLOSED" in out  # no --approved-cells


def test_dry_run_reports_gate_open_with_approved_cells(monkeypatch, capsys):
    module = _load()
    monkeypatch.setattr(sys, "argv", ["run_stage7.py", "--dry-run", "--approved-cells", "cells.json"])
    assert module.main() == 0
    assert "Generation gate: OPEN" in capsys.readouterr().out
