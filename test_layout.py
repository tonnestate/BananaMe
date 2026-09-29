from pathlib import Path


def test_python_package_has_no_nested_subpackages() -> None:
    root = Path(__file__).resolve().parents[1]
    package = root / "src" / "bananame"
    nested = [p for p in package.iterdir() if p.is_dir() and p.name != "__pycache__"]
    assert nested == []


def test_packaged_skill_is_shallow() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "src" / "bananame" / "SKILL.md").is_file()
    assert (root / "skill" / "SKILL.md").is_file()
