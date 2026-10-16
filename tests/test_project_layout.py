from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_phase_zero_layout_exists() -> None:
    for relative in (
        "README.md",
        "requirements.txt",
        "scripts/build_dataset.py",
        "scripts/validate_dataset.py",
        "scripts/legacy/build_sequence.py",
        "scripts/legacy/validate_sequence.py",
    ):
        assert (ROOT / relative).is_file(), relative
