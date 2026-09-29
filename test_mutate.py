from __future__ import annotations

import hashlib
from pathlib import Path

from bananame.core import BananaMe


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_apply_and_conflict_safe_rollback(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text("def value():\n    return 1\n", encoding="utf-8")
    tool = BananaMe(str(tmp_path))
    result = tool.mutate(edits=[{
        "path": "a.py",
        "search": "    return 1\n",
        "replace": "    return 2\n",
        "expected_sha256": digest(target),
    }])
    assert result["ok"] is True
    assert target.read_text("utf-8").endswith("return 2\n")

    target.write_text("def value():\n    return 3\n", encoding="utf-8")
    rollback = tool.mutate(action="rollback", transaction_id=result["transaction_id"])
    assert rollback["ok"] is False
    assert rollback["error"]["code"] == "ROLLBACK_CONFLICT"
    assert target.read_text("utf-8").endswith("return 3\n")


def test_ambiguous_search_fails_without_write(tmp_path: Path) -> None:
    target = tmp_path / "x.txt"
    target.write_text("same\nsame\n", encoding="utf-8")
    before = target.read_bytes()
    tool = BananaMe(str(tmp_path))
    result = tool.mutate(edits=[{
        "path": "x.txt",
        "search": "same",
        "replace": "different",
        "expected_sha256": digest(target),
    }])
    assert result["ok"] is False
    assert result["error"]["code"] == "SEARCH_AMBIGUOUS"
    assert target.read_bytes() == before


def test_crlf_is_preserved(tmp_path: Path) -> None:
    target = tmp_path / "crlf.py"
    target.write_bytes(b"def x():\r\n    return 1\r\n")
    tool = BananaMe(str(tmp_path))
    result = tool.mutate(edits=[{
        "path": "crlf.py",
        "search": "    return 1\n",
        "replace": "    return 2\n",
        "expected_sha256": digest(target),
    }])
    assert result["ok"] is True
    raw = target.read_bytes()
    assert b"\r\n" in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")


def test_multi_file_syntax_preflight_is_all_or_nothing(tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("x = 1\n", encoding="utf-8")
    b.write_text("y = 2\n", encoding="utf-8")
    before_a = a.read_bytes()
    before_b = b.read_bytes()
    tool = BananaMe(str(tmp_path))
    result = tool.mutate(edits=[
        {"path": "a.py", "search": "x = 1\n", "replace": "x = 3\n", "expected_sha256": digest(a)},
        {"path": "b.py", "search": "y = 2\n", "replace": "def broken(:\n", "expected_sha256": digest(b)},
    ])
    assert result["ok"] is False
    assert result["error"]["code"] == "SYNTAX_PREFLIGHT_FAILED"
    assert a.read_bytes() == before_a
    assert b.read_bytes() == before_b


def test_successful_rollback_restores_original(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    original = target.read_bytes()
    tool = BananaMe(str(tmp_path))
    applied = tool.mutate(edits=[{
        "path": "a.py", "search": "x = 1\n", "replace": "x = 2\n", "expected_sha256": digest(target)
    }])
    assert applied["ok"] is True
    rolled = tool.mutate(action="rollback", transaction_id=applied["transaction_id"])
    assert rolled["ok"] is True
    assert target.read_bytes() == original
