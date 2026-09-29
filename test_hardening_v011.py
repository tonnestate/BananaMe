from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from bananame.core import BananaMe
from bananame.mutate import _incomplete_transactions
from bananame.understand import _inventory
from bananame.workspace import Workspace


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_overlapping_edits_fail_closed(tmp_path: Path) -> None:
    target = tmp_path / "x.txt"
    target.write_text("abcdef\n", encoding="utf-8")
    tool = BananaMe(str(tmp_path))
    result = tool.mutate(edits=[
        {"path": "x.txt", "search": "abcde", "replace": "A", "expected_sha256": digest(target)},
        {"path": "x.txt", "search": "cdef", "replace": "B", "expected_sha256": digest(target)},
    ])
    assert result["ok"] is False
    assert result["error"]["code"] == "EDIT_OVERLAP"
    assert target.read_text("utf-8") == "abcdef\n"


def test_non_overlapping_edits_resolve_against_original_snapshot(tmp_path: Path) -> None:
    target = tmp_path / "x.txt"
    target.write_text("one two three\n", encoding="utf-8")
    tool = BananaMe(str(tmp_path))
    result = tool.mutate(edits=[
        {"path": "x.txt", "search": "three", "replace": "THREE", "expected_sha256": digest(target)},
        {"path": "x.txt", "search": "one", "replace": "ONE", "expected_sha256": digest(target)},
    ])
    assert result["ok"] is True
    assert target.read_text("utf-8") == "ONE two THREE\n"


def test_mutation_lock_refuses_parallel_commit_phase(tmp_path: Path) -> None:
    target = tmp_path / "x.txt"
    target.write_text("x = 1\n", encoding="utf-8")
    tool = BananaMe(str(tmp_path))
    ws = Workspace(tmp_path)
    with ws.mutation_lock():
        result = tool.mutate(edits=[{
            "path": "x.txt", "search": "1", "replace": "2", "expected_sha256": digest(target)
        }])
    assert result["ok"] is False
    assert result["error"]["code"] == "MUTATION_BUSY"
    assert _incomplete_transactions(ws) == []


def test_recover_mixed_crash_state_rolls_back(tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a_before = b"a = 1\n"
    b_before = b"b = 1\n"
    a_after = b"a = 2\n"
    b_after = b"b = 2\n"
    a.write_bytes(a_after)
    b.write_bytes(b_before)

    txid = "deadbeef"
    tx = tmp_path / ".bananame" / "transactions" / txid
    (tx / "before").mkdir(parents=True)
    (tx / "before" / "a.py").write_bytes(a_before)
    (tx / "before" / "b.py").write_bytes(b_before)
    manifest = {
        "schema": "bananame-transaction/2",
        "transaction_id": txid,
        "status": "APPLYING",
        "changed_files": ["a.py", "b.py"],
        "before_hashes": {
            "a.py": hashlib.sha256(a_before).hexdigest(),
            "b.py": hashlib.sha256(b_before).hexdigest(),
        },
        "after_hashes": {
            "a.py": hashlib.sha256(a_after).hexdigest(),
            "b.py": hashlib.sha256(b_after).hexdigest(),
        },
        "file_states": {"a.py": "APPLIED", "b.py": "PENDING"},
    }
    (tx / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = BananaMe(str(tmp_path)).mutate(action="recover", transaction_id=txid)
    assert result["ok"] is True
    assert result["status"] == "ROLLED_BACK_RECOVERED"
    assert a.read_bytes() == a_before
    assert b.read_bytes() == b_before


def test_recover_all_after_marks_applied(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    before = b"a = 1\n"
    after = b"a = 2\n"
    target.write_bytes(after)
    txid = "allafter"
    tx = tmp_path / ".bananame" / "transactions" / txid
    (tx / "before").mkdir(parents=True)
    (tx / "before" / "a.py").write_bytes(before)
    manifest = {
        "schema": "bananame-transaction/2",
        "transaction_id": txid,
        "status": "APPLYING",
        "changed_files": ["a.py"],
        "before_hashes": {"a.py": hashlib.sha256(before).hexdigest()},
        "after_hashes": {"a.py": hashlib.sha256(after).hexdigest()},
        "file_states": {"a.py": "APPLIED"},
    }
    (tx / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = BananaMe(str(tmp_path)).mutate(action="recover", transaction_id=txid)
    assert result["status"] == "APPLIED_RECOVERED"
    assert target.read_bytes() == after


def test_verify_unsupported_path_is_not_verified_without_other_evidence(tmp_path: Path) -> None:
    target = tmp_path / "x.ts"
    target.write_text("const x: number = 1;\n", encoding="utf-8")
    result = BananaMe(str(tmp_path)).verify(paths=["x.ts"])
    assert result["ok"] is False
    assert result["execution_ok"] is True
    assert result["status"] == "NOT_VERIFIED"
    assert result["evidence"]["syntax_skipped"] == 1


def test_verify_mixed_supported_and_unsupported_is_partial(tmp_path: Path) -> None:
    (tmp_path / "x.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "x.ts").write_text("const x: number = 1;\n", encoding="utf-8")
    result = BananaMe(str(tmp_path)).verify(paths=["x.py", "x.ts"])
    assert result["ok"] is False
    assert result["status"] == "PARTIAL"
    assert result["evidence"]["syntax_passed"] == 1
    assert result["evidence"]["syntax_skipped"] == 1


def test_verify_without_any_evidence_is_not_verified(tmp_path: Path) -> None:
    result = BananaMe(str(tmp_path)).verify()
    assert result["ok"] is False
    assert result["status"] == "NOT_VERIFIED"
    assert result["evidence"]["checks_executed"] == 0


def test_verify_supported_syntax_can_be_verified(tmp_path: Path) -> None:
    target = tmp_path / "x.py"
    target.write_text("x = 1\n", encoding="utf-8")
    result = BananaMe(str(tmp_path)).verify(paths=["x.py"])
    assert result["ok"] is True
    assert result["status"] == "VERIFIED"


def test_inventory_discloses_truncation(tmp_path: Path) -> None:
    for i in range(4):
        (tmp_path / f"f{i}.txt").write_text(str(i), encoding="utf-8")
    inventory = _inventory(tmp_path, limit=2)
    assert inventory.truncated is True
    assert len(inventory.files) == 2


def test_exact_deep_path_returns_guarded_file_evidence(tmp_path: Path) -> None:
    target = tmp_path / "src" / "main" / "java" / "com" / "company" / "Auth.java"
    target.parent.mkdir(parents=True)
    target.write_text("class Auth {}\n", encoding="utf-8")
    result = BananaMe(str(tmp_path)).understand(query="src/main/java/com/company/Auth.java")
    assert result["ok"] is True
    assert result["exact_files"] == ["src/main/java/com/company/Auth.java"]
    assert result["file_evidence"][0]["sha256"] == digest(target)
    assert "class Auth" in result["file_evidence"][0]["content"]


def test_mutation_accepts_deep_target_repo_path(tmp_path: Path) -> None:
    target = tmp_path / "src" / "main" / "java" / "com" / "company" / "Auth.java"
    target.parent.mkdir(parents=True)
    target.write_text("class Auth { int x = 1; }\n", encoding="utf-8")
    result = BananaMe(str(tmp_path)).mutate(edits=[{
        "path": "src/main/java/com/company/Auth.java",
        "search": "x = 1",
        "replace": "x = 2",
        "expected_sha256": digest(target),
    }])
    assert result["ok"] is True
    assert "x = 2" in target.read_text("utf-8")


def test_binary_and_invalid_utf8_are_rejected(tmp_path: Path) -> None:
    binary = tmp_path / "binary.bin"
    binary.write_bytes(b"abc\x00def")
    invalid = tmp_path / "invalid.txt"
    invalid.write_bytes(b"\xff\xfe")
    tool = BananaMe(str(tmp_path))
    b = tool.understand(query="binary.bin")
    # understand omits unreadable exact evidence but mutation still fails closed.
    assert b["ok"] is True
    r1 = tool.mutate(edits=[{"path": "binary.bin", "search": "abc", "replace": "x", "expected_sha256": digest(binary)}])
    r2 = tool.mutate(edits=[{"path": "invalid.txt", "search": "x", "replace": "y", "expected_sha256": digest(invalid)}])
    assert r1["error"]["code"] == "BINARY_FILE_UNSUPPORTED"
    assert r2["error"]["code"] == "UTF8_REQUIRED"


def test_stale_head_remains_optional_strict_guard(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    target = tmp_path / "x.py"
    target.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "x.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "one"], cwd=tmp_path, check=True)
    old_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    # Unrelated HEAD movement; target file remains byte-identical.
    other = tmp_path / "other.txt"
    other.write_text("other\n", encoding="utf-8")
    subprocess.run(["git", "add", "other.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "two"], cwd=tmp_path, check=True)

    strict = BananaMe(str(tmp_path)).mutate(
        expected_head=old_head,
        edits=[{"path": "x.py", "search": "1", "replace": "2", "expected_sha256": digest(target)}],
    )
    assert strict["ok"] is False
    assert strict["error"]["code"] == "STALE_HEAD"

    target_scoped = BananaMe(str(tmp_path)).mutate(
        edits=[{"path": "x.py", "search": "1", "replace": "2", "expected_sha256": digest(target)}],
    )
    assert target_scoped["ok"] is True


def test_cochange_returns_historical_neighbor(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("needle = 1\n", encoding="utf-8")
    b.write_text("peer = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "together"], cwd=tmp_path, check=True)
    result = BananaMe(str(tmp_path)).understand(query="needle")
    assert any(item["path"] == "b.py" for item in result["cochange"])


def test_recover_legacy_v010_journal(tmp_path: Path) -> None:
    target = tmp_path / "legacy.py"
    before = b"x = 1\n"
    after = b"x = 2\n"
    target.write_bytes(after)
    txid = "legacyv1"
    tx = tmp_path / ".bananame" / "transactions" / txid
    (tx / "before").mkdir(parents=True)
    (tx / "before" / "legacy.py").write_bytes(before)
    manifest = {
        "schema": "bananame-transaction/1",
        "transaction_id": txid,
        "status": "PREPARED",
        "changed_files": ["legacy.py"],
        "before_hashes": {"legacy.py": hashlib.sha256(before).hexdigest()},
        "after_hashes": {},
        "edits": [{
            "path": "legacy.py",
            "search": "x = 1\n",
            "replace": "x = 2\n",
            "expected_sha256": hashlib.sha256(before).hexdigest(),
        }],
    }
    (tx / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = BananaMe(str(tmp_path)).mutate(action="recover", transaction_id=txid)
    assert result["status"] == "APPLIED_RECOVERED"
    upgraded = json.loads((tx / "manifest.json").read_text("utf-8"))
    assert upgraded["schema"] == "bananame-transaction/2"
    assert upgraded["upgraded_from"] == "bananame-transaction/1"


def test_context_budget_reports_truncation_without_exceeding_budget(tmp_path: Path) -> None:
    target = tmp_path / "large.py"
    target.write_text("\n".join(f"def f{i}(): return {i}" for i in range(200)) + "\n", encoding="utf-8")
    result = BananaMe(str(tmp_path)).understand(query="large.py", max_context_bytes=1024)
    assert result["context_bytes"] <= result["context_budget_bytes"]
    assert result["context_truncated"] is True
    assert result["file_evidence"][0]["sha256"] == digest(target)


def test_incomplete_transaction_blocks_new_mutation(tmp_path: Path) -> None:
    target = tmp_path / "x.py"
    target.write_text("x = 1\n", encoding="utf-8")
    tx = tmp_path / ".bananame" / "transactions" / "pending"
    tx.mkdir(parents=True)
    (tx / "manifest.json").write_text(json.dumps({
        "schema": "bananame-transaction/2",
        "transaction_id": "pending",
        "status": "APPLYING",
        "changed_files": [],
        "before_hashes": {},
        "after_hashes": {},
        "file_states": {},
    }), encoding="utf-8")
    result = BananaMe(str(tmp_path)).mutate(edits=[{
        "path": "x.py", "search": "1", "replace": "2", "expected_sha256": digest(target)
    }])
    assert result["ok"] is False
    assert result["error"]["code"] == "RECOVERY_REQUIRED"
    assert result["error"]["details"]["transaction_ids"] == ["pending"]


def test_many_hot_files_never_exceed_context_budget(tmp_path: Path) -> None:
    hot = []
    for i in range(50):
        target = tmp_path / f"f{i}.py"
        target.write_text("x = 1\n", encoding="utf-8")
        hot.append(target.name)
    result = BananaMe(str(tmp_path)).understand(hot_files=hot, max_context_bytes=1024)
    assert result["context_bytes"] <= result["context_budget_bytes"]
    assert result["file_evidence_truncated"] is True
    assert result["file_evidence_returned"] < result["file_evidence_requested"]
    assert result["context_truncated"] is True
