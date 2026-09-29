from __future__ import annotations

import difflib
import json
import os
import stat
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .errors import BananaMeError
from .git import head_revision
from .verify import syntax_check_text
from .workspace import Workspace, sha256_bytes


@dataclass(frozen=True)
class Edit:
    path: str
    search: str
    replace: str
    expected_sha256: str


def _newline_adapt(text: str, newline: str) -> str:
    normalized = text.replace("\r\n", "\n")
    return normalized.replace("\n", newline) if newline == "\r\n" else normalized


def _unified_diff(path: str, before: str, after: str) -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    ))


def _transaction_dir(ws: Workspace, transaction_id: str) -> Path:
    return ws.internal_dir("transactions", transaction_id)


def _write_manifest(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def apply_mutation(
    workspace_root: str,
    edits: list[dict[str, str]],
    expected_head: str | None = None,
) -> dict[str, Any]:
    ws = Workspace(workspace_root)
    current_head = head_revision(ws.root)
    if expected_head is not None and current_head != expected_head:
        raise BananaMeError(
            "STALE_HEAD",
            "Repository HEAD changed since planning.",
            details={"expected_head": expected_head, "actual_head": current_head},
        )
    if not edits:
        raise BananaMeError("NO_EDITS", "At least one edit is required.")

    parsed: list[Edit] = []
    for raw in edits:
        missing = [key for key in ("path", "search", "replace", "expected_sha256") if key not in raw]
        if missing:
            raise BananaMeError("INVALID_EDIT", f"Missing edit fields: {', '.join(missing)}")
        parsed.append(Edit(
            path=str(raw["path"]).replace("\\", "/"),
            search=str(raw["search"]),
            replace=str(raw["replace"]),
            expected_sha256=str(raw["expected_sha256"]),
        ))

    grouped: dict[str, list[Edit]] = defaultdict(list)
    for edit in parsed:
        grouped[edit.path].append(edit)

    before: dict[str, Any] = {}
    after_text: dict[str, str] = {}
    syntax_preflight: list[dict[str, Any]] = []
    diffs: list[str] = []

    for path, path_edits in grouped.items():
        snap = ws.read_text(path)
        if snap.sha256 != path_edits[0].expected_sha256:
            raise BananaMeError(
                "STALE_FILE",
                f"File changed since it was read: {path}",
                details={"path": path, "expected_sha256": path_edits[0].expected_sha256, "actual_sha256": snap.sha256},
            )
        if any(edit.expected_sha256 != snap.sha256 for edit in path_edits):
            raise BananaMeError("INCONSISTENT_FILE_GUARD", f"All edits for {path} must use the same initial expected_sha256.")
        current = snap.text
        for index, edit in enumerate(path_edits):
            search = _newline_adapt(edit.search, snap.newline)
            replace = _newline_adapt(edit.replace, snap.newline)
            matches = current.count(search)
            if matches == 0:
                raise BananaMeError(
                    "SEARCH_NOT_FOUND",
                    f"SEARCH block does not exactly match current source: {path}",
                    details={"path": path, "edit_index": index},
                )
            if matches > 1:
                raise BananaMeError(
                    "SEARCH_AMBIGUOUS",
                    f"SEARCH block matches more than once: {path}",
                    details={"path": path, "edit_index": index, "match_count": matches},
                )
            current = current.replace(search, replace, 1)
        preflight = syntax_check_text(path, current)
        syntax_preflight.append(preflight)
        if preflight["status"] == "FAIL":
            raise BananaMeError(
                "SYNTAX_PREFLIGHT_FAILED",
                f"Mutation would produce invalid syntax in {path}",
                details=preflight,
            )
        before[path] = snap
        after_text[path] = current
        diffs.append(_unified_diff(path, snap.text, current))

    transaction_id = uuid.uuid4().hex
    tx = _transaction_dir(ws, transaction_id)
    backup_root = tx / "before"
    backup_root.mkdir(parents=True, exist_ok=True)
    changed_files = sorted(grouped)
    manifest: dict[str, Any] = {
        "schema": "bananame-transaction/1",
        "transaction_id": transaction_id,
        "status": "PREPARED",
        "base_head": current_head,
        "changed_files": changed_files,
        "before_hashes": {path: before[path].sha256 for path in changed_files},
        "after_hashes": {},
        "edits": [asdict(edit) | {"expected_sha256": edit.expected_sha256} for edit in parsed],
        "syntax_preflight": syntax_preflight,
    }
    for path in changed_files:
        backup = backup_root / path
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(before[path].raw)
    (tx / "diff.patch").write_text("".join(diffs), encoding="utf-8")
    _write_manifest(tx / "manifest.json", manifest)

    written: list[str] = []
    try:
        for path in changed_files:
            raw = after_text[path].encode("utf-8")
            ws.atomic_write(path, raw, mode=before[path].mode)
            written.append(path)
        after_hashes = {path: sha256_bytes(after_text[path].encode("utf-8")) for path in changed_files}
        manifest["after_hashes"] = after_hashes
        manifest["status"] = "APPLIED"
        _write_manifest(tx / "manifest.json", manifest)
    except Exception as exc:
        for path in reversed(written):
            ws.atomic_write(path, before[path].raw, mode=before[path].mode)
        manifest["status"] = "ROLLED_BACK"
        manifest["rollback_reason"] = str(exc)
        _write_manifest(tx / "manifest.json", manifest)
        raise BananaMeError("WRITE_FAILED_ROLLED_BACK", "Mutation failed and written files were restored.", details={"error": str(exc)}) from exc

    return {
        "ok": True,
        "operation": "mutate",
        "action": "apply",
        "status": "APPLIED",
        "transaction_id": transaction_id,
        "base_head": current_head,
        "changed_files": changed_files,
        "before_hashes": manifest["before_hashes"],
        "after_hashes": manifest["after_hashes"],
        "syntax_preflight": syntax_preflight,
        "diff": "".join(diffs),
        "commit_created": False,
    }


def rollback_mutation(workspace_root: str, transaction_id: str) -> dict[str, Any]:
    ws = Workspace(workspace_root)
    tx = ws.root / ".bananame" / "transactions" / transaction_id
    manifest_path = tx / "manifest.json"
    if not manifest_path.is_file():
        raise BananaMeError("TRANSACTION_NOT_FOUND", f"Unknown transaction: {transaction_id}")
    manifest = json.loads(manifest_path.read_text("utf-8"))
    changed_files = list(manifest.get("changed_files") or [])
    after_hashes = dict(manifest.get("after_hashes") or {})

    # Refuse to erase work that happened after this transaction.
    for path in changed_files:
        snap = ws.read_text(path)
        expected = after_hashes.get(path)
        if expected and snap.sha256 != expected:
            raise BananaMeError(
                "ROLLBACK_CONFLICT",
                f"File changed after transaction; rollback refused: {path}",
                details={"path": path, "expected_current_sha256": expected, "actual_sha256": snap.sha256},
            )

    for path in changed_files:
        backup = tx / "before" / path
        if not backup.is_file():
            raise BananaMeError("ROLLBACK_BACKUP_MISSING", f"Backup missing for {path}", recoverable=False)
        original = backup.read_bytes()
        current_mode = ws.resolve(path).stat().st_mode
        ws.atomic_write(path, original, mode=current_mode)

    manifest["status"] = "ROLLED_BACK"
    _write_manifest(manifest_path, manifest)
    return {
        "ok": True,
        "operation": "mutate",
        "action": "rollback",
        "status": "ROLLED_BACK",
        "transaction_id": transaction_id,
        "changed_files": changed_files,
    }


def mutate(
    workspace_root: str,
    edits: list[dict[str, str]] | None = None,
    expected_head: str | None = None,
    action: str = "apply",
    transaction_id: str | None = None,
) -> dict[str, Any]:
    if action == "apply":
        return apply_mutation(workspace_root, edits or [], expected_head=expected_head)
    if action == "rollback":
        if not transaction_id:
            raise BananaMeError("TRANSACTION_ID_REQUIRED", "rollback requires transaction_id")
        return rollback_mutation(workspace_root, transaction_id)
    raise BananaMeError("INVALID_MUTATION_ACTION", "action must be 'apply' or 'rollback'")
