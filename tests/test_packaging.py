from importlib.resources import files
from pathlib import Path


def test_packaged_skill_exists_and_matches_repository_mirror() -> None:
    packaged = (files("bananame") / "SKILL.md").read_text(encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    mirror = (root / "skill" / "SKILL.md").read_text(encoding="utf-8")
    assert packaged == mirror
