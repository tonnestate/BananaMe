from __future__ import annotations

import json
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_portable_skill_path_exists_and_mirrors_match() -> None:
    root = _root()
    portable = (root / "skills" / "bananame" / "SKILL.md").read_bytes()
    legacy = (root / "skill" / "SKILL.md").read_bytes()
    packaged = (root / "src" / "bananame" / "SKILL.md").read_bytes()
    assert portable == legacy == packaged


def test_portable_plugin_manifest_matches_release() -> None:
    root = _root()
    data = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
    assert data["name"] == "bananame"
    assert data["version"] == "0.1.2"
    assert data["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


def test_skill_is_immediate_child_of_skills_directory() -> None:
    root = _root()
    manifests = sorted((root / "skills").glob("*/SKILL.md"))
    assert manifests == [root / "skills" / "bananame" / "SKILL.md"]
