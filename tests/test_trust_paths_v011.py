from __future__ import annotations

import hashlib
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

from bananame.core import BananaMe
from bananame.workspace import Workspace


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_write_failure_restores_already_written_files(tmp_path: Path, monkeypatch) -> None:
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("a = 1\n", encoding="utf-8")
    b.write_text("b = 1\n", encoding="utf-8")
    original = Workspace.atomic_write
    calls = {"count": 0}

    def flaky(self: Workspace, relative_path: str, raw: bytes, *, mode=None) -> None:
        if relative_path in {"a.py", "b.py"}:
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("simulated write failure")
        return original(self, relative_path, raw, mode=mode)

    monkeypatch.setattr(Workspace, "atomic_write", flaky)
    result = BananaMe(str(tmp_path)).mutate(edits=[
        {"path": "a.py", "search": "1", "replace": "2", "expected_sha256": digest(a)},
        {"path": "b.py", "search": "1", "replace": "2", "expected_sha256": digest(b)},
    ])
    assert result["ok"] is False
    assert result["error"]["code"] == "WRITE_FAILED_ROLLED_BACK"
    # The first source write must not survive a handled write-phase failure.
    assert a.read_text("utf-8") == "a = 1\n"
    assert b.read_text("utf-8") == "b = 1\n"


def test_target_revalidated_after_preflight(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "x.py"
    target.write_text("x = 1\n", encoding="utf-8")
    observed = digest(target)
    original_lock = Workspace.mutation_lock

    @contextmanager
    def change_before_commit(self: Workspace):
        with original_lock(self):
            target.write_text("x = 9\n", encoding="utf-8")
            yield

    monkeypatch.setattr(Workspace, "mutation_lock", change_before_commit)
    result = BananaMe(str(tmp_path)).mutate(edits=[{
        "path": "x.py", "search": "1", "replace": "2", "expected_sha256": observed
    }])
    assert result["ok"] is False
    assert result["error"]["code"] == "STALE_FILE"
    assert target.read_text("utf-8") == "x = 9\n"


def test_recovery_conflict_preserves_unknown_bytes(tmp_path: Path) -> None:
    target = tmp_path / "x.py"
    before = b"x = 1\n"
    after = b"x = 2\n"
    unknown = b"x = 3\n"
    target.write_bytes(unknown)
    txid = "conflict"
    tx = tmp_path / ".bananame" / "transactions" / txid
    (tx / "before").mkdir(parents=True)
    (tx / "before" / "x.py").write_bytes(before)
    (tx / "manifest.json").write_text(json.dumps({
        "schema": "bananame-transaction/2",
        "transaction_id": txid,
        "status": "APPLYING",
        "changed_files": ["x.py"],
        "before_hashes": {"x.py": hashlib.sha256(before).hexdigest()},
        "after_hashes": {"x.py": hashlib.sha256(after).hexdigest()},
        "file_states": {"x.py": "APPLIED"},
    }), encoding="utf-8")
    result = BananaMe(str(tmp_path)).mutate(action="recover", transaction_id=txid)
    assert result["ok"] is False
    assert result["error"]["code"] == "RECOVERY_CONFLICT"
    assert target.read_bytes() == unknown


def test_verify_builtin_formats_and_command_states(tmp_path: Path) -> None:
    (tmp_path / "x.json").write_text('{"x": 1}\n', encoding="utf-8")
    (tmp_path / "x.toml").write_text('x = 1\n', encoding="utf-8")
    (tmp_path / "x.xml").write_text('<x/>\n', encoding="utf-8")
    tool = BananaMe(str(tmp_path))
    passed = tool.verify(
        paths=["x.json", "x.toml", "x.xml"],
        commands=[[sys.executable, "-c", "print('ok')"]],
    )
    assert passed["status"] == "VERIFIED"
    assert passed["evidence"]["syntax_passed"] == 3
    assert passed["evidence"]["commands_passed"] == 1

    failed = tool.verify(commands=[[sys.executable, "-c", "raise SystemExit(7)"]])
    assert failed["status"] == "VERIFICATION_FAILED"
    assert failed["commands"][0]["exit_code"] == 7

    missing = tool.verify(commands=[["bananame-command-that-does-not-exist"]])
    assert missing["status"] == "VERIFICATION_FAILED"
    assert missing["commands"][0]["error"] == "COMMAND_NOT_FOUND"


def test_verify_invalid_builtin_syntax_fails(tmp_path: Path) -> None:
    (tmp_path / "x.json").write_text('{broken', encoding="utf-8")
    result = BananaMe(str(tmp_path)).verify(paths=["x.json"])
    assert result["status"] == "VERIFICATION_FAILED"
    assert result["evidence"]["syntax_failed"] == 1


def test_verify_transaction_loads_changed_paths(tmp_path: Path) -> None:
    target = tmp_path / "x.py"
    target.write_text("x = 1\n", encoding="utf-8")
    tool = BananaMe(str(tmp_path))
    applied = tool.mutate(edits=[{
        "path": "x.py", "search": "1", "replace": "2", "expected_sha256": digest(target)
    }])
    verified = tool.verify(transaction_id=applied["transaction_id"])
    assert verified["status"] == "VERIFIED"
    assert verified["paths"] == ["x.py"]


def test_internal_bananame_symlink_is_denied(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".bananame").symlink_to(outside, target_is_directory=True)
    target = tmp_path / "x.py"
    target.write_text("x = 1\n", encoding="utf-8")
    result = BananaMe(str(tmp_path)).mutate(edits=[{
        "path": "x.py", "search": "1", "replace": "2", "expected_sha256": digest(target)
    }])
    assert result["ok"] is False
    assert result["error"]["code"] == "INTERNAL_SYMLINK_DENIED"
    assert target.read_text("utf-8") == "x = 1\n"
    assert list(outside.iterdir()) == []


def test_transaction_id_cannot_escape_internal_store(tmp_path: Path) -> None:
    result = BananaMe(str(tmp_path)).mutate(action="recover", transaction_id="../../outside")
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_TRANSACTION_ID"
