from __future__ import annotations

import difflib
import json
import os
import re
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .errors import BananaMeError
from .git import head_revision
from .verify import syntax_check_text
from .workspace import Workspace, sha256_bytes


_INCOMPLETE_STATUSES = {"PREPARED", "APPLYING", "RECOVERING", "RECOVERY_REQUIRED"}
_TRANSACTION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _validate_transaction_id(transaction_id: str) -> str:
    if not _TRANSACTION_ID_RE.fullmatch(transaction_id):
        raise BananaMeError(
            "INVALID_TRANSACTION_ID",
            "transaction_id must contain only letters, digits, underscore or hyphen (1-64 characters).",
        )
    return transaction_id


@dataclass(frozen=True)
class Edit:
    path: str
    search: str
    replace: str
    expected_sha256: str


@dataclass(frozen=True)
class ResolvedEdit:
    index: int
    start: int
    end: int
    search: str
    replace: str


def _newline_adapt(text: str, newline: str) -> str:
    normalized = text.replace("\r\n", "\n")
    return normalized.replace("\n", newline) if newline == "\r\n" else normalized


def _unified_diff(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def _transaction_dir(ws: Workspace, transaction_id: str) -> Path:
    return ws.internal_dir("transactions", _validate_transaction_id(transaction_id))


def _write_manifest(ws: Workspace, path: Path, data: dict[str, Any]) -> None:
    raw = json.dumps(data, indent=2, sort_keys=True).encode("utf-8")
    ws.atomic_write_internal(path, raw)


def _durable_write(ws: Workspace, path: Path, raw: bytes) -> None:
    ws.atomic_write_internal(path, raw)


def _find_occurrences(text: str, needle: str) -> list[int]:
    if not needle:
        return []
    out: list[int] = []
    start = 0
    while True:
        pos = text.find(needle, start)
        if pos < 0:
            return out
        out.append(pos)
        if len(out) > 1:
            return out
        start = pos + 1


def _resolve_file_edits(path: str, path_edits: list[Edit], text: str, newline: str) -> tuple[str, list[ResolvedEdit]]:
    resolved: list[ResolvedEdit] = []
    for index, edit in enumerate(path_edits):
        if not edit.search:
            raise BananaMeError("INVALID_EDIT", "SEARCH block must not be empty.", details={"path": path, "edit_index": index})
        search = _newline_adapt(edit.search, newline)
        replace = _newline_adapt(edit.replace, newline)
        occurrences = _find_occurrences(text, search)
        if not occurrences:
            raise BananaMeError(
                "SEARCH_NOT_FOUND",
                f"SEARCH block does not exactly match observed source: {path}",
                details={"path": path, "edit_index": index},
            )
        if len(occurrences) > 1:
            raise BananaMeError(
                "SEARCH_AMBIGUOUS",
                f"SEARCH block matches more than once in observed source: {path}",
                details={"path": path, "edit_index": index, "match_count": len(occurrences)},
            )
        start = occurrences[0]
        resolved.append(ResolvedEdit(index=index, start=start, end=start + len(search), search=search, replace=replace))

    by_position = sorted(resolved, key=lambda item: (item.start, item.end))
    for left, right in zip(by_position, by_position[1:]):
        if right.start < left.end:
            raise BananaMeError(
                "EDIT_OVERLAP",
                f"Two edits overlap in the same observed file: {path}",
                details={
                    "path": path,
                    "left_edit_index": left.index,
                    "right_edit_index": right.index,
                    "left_span": [left.start, left.end],
                    "right_span": [right.start, right.end],
                },
            )

    current = text
    for item in sorted(resolved, key=lambda value: value.start, reverse=True):
        current = current[: item.start] + item.replace + current[item.end :]
    return current, resolved


def _load_manifest(ws: Workspace, transaction_id: str) -> tuple[Path, dict[str, Any]]:
    transaction_id = _validate_transaction_id(transaction_id)
    tx = ws.root / ".bananame" / "transactions" / transaction_id
    manifest_path = tx / "manifest.json"
    if not manifest_path.is_file():
        raise BananaMeError("TRANSACTION_NOT_FOUND", f"Unknown transaction: {transaction_id}")
    try:
        manifest = json.loads(manifest_path.read_text("utf-8"))
    except Exception as exc:
        raise BananaMeError("TRANSACTION_MANIFEST_INVALID", f"Cannot read transaction manifest: {transaction_id}", recoverable=False) from exc
    return manifest_path, manifest


def _incomplete_transactions(ws: Workspace) -> list[str]:
    root = ws.root / ".bananame" / "transactions"
    if not root.is_dir():
        return []
    out: list[str] = []
    for manifest_path in sorted(root.glob("*/manifest.json")):
        try:
            data = json.loads(manifest_path.read_text("utf-8"))
        except Exception:
            out.append(manifest_path.parent.name)
            continue
        if str(data.get("status")) in _INCOMPLETE_STATUSES:
            out.append(str(data.get("transaction_id") or manifest_path.parent.name))
    return out


def _require_no_incomplete(ws: Workspace) -> None:
    pending = _incomplete_transactions(ws)
    if pending:
        raise BananaMeError(
            "RECOVERY_REQUIRED",
            "An incomplete BananaMe transaction must be recovered before a new mutation starts.",
            details={"transaction_ids": pending},
        )


def _persist_backup(ws: Workspace, path: Path, raw: bytes) -> None:
    _durable_write(ws, path, raw)


def apply_mutation(
    workspace_root: str,
    edits: list[dict[str, str]],
    expected_head: str | None = None,
) -> dict[str, Any]:
    ws = Workspace(workspace_root)
    _require_no_incomplete(ws)
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
        parsed.append(
            Edit(
                path=str(raw["path"]).replace("\\", "/"),
                search=str(raw["search"]),
                replace=str(raw["replace"]),
                expected_sha256=str(raw["expected_sha256"]),
            )
        )

    grouped: dict[str, list[Edit]] = defaultdict(list)
    for edit in parsed:
        grouped[edit.path].append(edit)

    before: dict[str, Any] = {}
    after_text: dict[str, str] = {}
    resolved_edits: dict[str, list[ResolvedEdit]] = {}
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
        current, resolved = _resolve_file_edits(path, path_edits, snap.text, snap.newline)
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
        resolved_edits[path] = resolved
        diffs.append(_unified_diff(path, snap.text, current))

    transaction_id = uuid.uuid4().hex
    changed_files = sorted(grouped)
    before_hashes = {path: before[path].sha256 for path in changed_files}
    after_hashes = {path: sha256_bytes(after_text[path].encode("utf-8")) for path in changed_files}
    manifest: dict[str, Any] = {
        "schema": "bananame-transaction/2",
        "transaction_id": transaction_id,
        "status": "PREPARED",
        "base_head": current_head,
        "strict_expected_head": expected_head,
        "changed_files": changed_files,
        "before_hashes": before_hashes,
        "after_hashes": after_hashes,
        "file_states": {path: "PENDING" for path in changed_files},
        "edits": [asdict(edit) for edit in parsed],
        "resolved_spans": {
            path: [{"edit_index": r.index, "start": r.start, "end": r.end} for r in resolved_edits[path]]
            for path in changed_files
        },
        "syntax_preflight": syntax_preflight,
    }

    written: list[str] = []
    rollback_conflicts: list[dict[str, str]] = []
    tx: Path | None = None
    try:
        with ws.mutation_lock():
            if expected_head is not None:
                locked_head = head_revision(ws.root)
                if locked_head != expected_head:
                    raise BananaMeError(
                        "STALE_HEAD",
                        "Repository HEAD changed before the commit phase.",
                        details={"expected_head": expected_head, "actual_head": locked_head},
                    )

            stale: list[dict[str, str]] = []
            for path in changed_files:
                snap = ws.read_text(path)
                if snap.sha256 != before_hashes[path]:
                    stale.append({"path": path, "expected_sha256": before_hashes[path], "actual_sha256": snap.sha256})
            if stale:
                raise BananaMeError(
                    "STALE_FILE",
                    "One or more mutation targets changed during preflight.",
                    details={"files": stale},
                )

            # Journal-before-data: no source write occurs until before-images and PREPARED state are durable.
            tx = _transaction_dir(ws, transaction_id)
            backup_root = ws.internal_dir("transactions", transaction_id, "before")
            for path in changed_files:
                _persist_backup(ws, backup_root / path, before[path].raw)
            _durable_write(ws, tx / "diff.patch", "".join(diffs).encode("utf-8"))
            _write_manifest(ws, tx / "manifest.json", manifest)
            manifest["status"] = "APPLYING"
            _write_manifest(ws, tx / "manifest.json", manifest)

            for path in changed_files:
                # Final optimistic-concurrency validation immediately before each write.
                snap = ws.read_text(path)
                if snap.sha256 != before_hashes[path]:
                    raise BananaMeError(
                        "STALE_FILE",
                        f"Mutation target changed immediately before write: {path}",
                        details={"path": path, "expected_sha256": before_hashes[path], "actual_sha256": snap.sha256},
                    )
                raw = after_text[path].encode("utf-8")
                ws.atomic_write(path, raw, mode=before[path].mode)
                written.append(path)
                applied = ws.read_text(path)
                if applied.sha256 != after_hashes[path]:
                    raise BananaMeError(
                        "POST_WRITE_HASH_MISMATCH",
                        f"Written file does not match intended post-image: {path}",
                        recoverable=False,
                    )
                manifest["file_states"][path] = "APPLIED"
                _write_manifest(ws, tx / "manifest.json", manifest)

            manifest["status"] = "APPLIED"
            _write_manifest(ws, tx / "manifest.json", manifest)
    except BananaMeError as exc:
        if tx is None and not written:
            raise
        try:
            with ws.mutation_lock():
                for path in reversed(written):
                    try:
                        current = ws.read_text(path)
                        if current.sha256 != after_hashes[path]:
                            rollback_conflicts.append({"path": path, "actual_sha256": current.sha256})
                            continue
                        ws.atomic_write(path, before[path].raw, mode=before[path].mode)
                        manifest["file_states"][path] = "ROLLED_BACK"
                        _write_manifest(ws, tx / "manifest.json", manifest)
                    except Exception as rollback_exc:
                        rollback_conflicts.append({"path": path, "error": str(rollback_exc)})
        except BananaMeError as rollback_lock_exc:
            rollback_conflicts.append({"path": "<workspace>", "error": rollback_lock_exc.code})
        manifest["rollback_reason"] = exc.message
        if rollback_conflicts:
            manifest["status"] = "RECOVERY_REQUIRED"
            manifest["rollback_conflicts"] = rollback_conflicts
            if tx is not None:
                _write_manifest(ws, tx / "manifest.json", manifest)
            raise BananaMeError(
                "WRITE_FAILED_RECOVERY_REQUIRED",
                "Mutation failed and automatic rollback could not safely restore every file.",
                recoverable=False,
                details={"transaction_id": transaction_id, "conflicts": rollback_conflicts, "cause": exc.as_dict()},
            ) from exc
        manifest["status"] = "ROLLED_BACK"
        if tx is not None:
            _write_manifest(ws, tx / "manifest.json", manifest)
        raise
    except Exception as exc:
        # Catchable process-level failures (for example an OSError from a source
        # write) get the same ownership-aware rollback attempt as structured
        # BananaMe failures. A hard process/OS crash cannot execute this block;
        # that case is handled on restart through the durable journal/recover path.
        if tx is None and not written:
            raise BananaMeError(
                "WRITE_FAILED_BEFORE_JOURNAL",
                "Mutation failed before a recoverable transaction journal was created.",
                recoverable=False,
                details={"transaction_id": transaction_id, "error": str(exc)},
            ) from exc
        try:
            with ws.mutation_lock():
                for path in reversed(written):
                    try:
                        current = ws.read_text(path)
                        if current.sha256 != after_hashes[path]:
                            rollback_conflicts.append({"path": path, "actual_sha256": current.sha256})
                            continue
                        ws.atomic_write(path, before[path].raw, mode=before[path].mode)
                        manifest["file_states"][path] = "ROLLED_BACK"
                        _write_manifest(ws, tx / "manifest.json", manifest)
                    except Exception as rollback_exc:
                        rollback_conflicts.append({"path": path, "error": str(rollback_exc)})
        except BananaMeError as rollback_lock_exc:
            rollback_conflicts.append({"path": "<workspace>", "error": rollback_lock_exc.code})

        manifest["rollback_reason"] = str(exc)
        if rollback_conflicts:
            manifest["status"] = "RECOVERY_REQUIRED"
            manifest["rollback_conflicts"] = rollback_conflicts
            if tx is not None:
                _write_manifest(ws, tx / "manifest.json", manifest)
            raise BananaMeError(
                "WRITE_FAILED_RECOVERY_REQUIRED",
                "Mutation failed and automatic rollback could not safely restore every file.",
                recoverable=False,
                details={"transaction_id": transaction_id, "conflicts": rollback_conflicts, "error": str(exc)},
            ) from exc

        manifest["status"] = "ROLLED_BACK"
        if tx is not None:
            _write_manifest(ws, tx / "manifest.json", manifest)
        raise BananaMeError(
            "WRITE_FAILED_ROLLED_BACK",
            "Mutation failed and all source writes made by this transaction were restored.",
            details={"transaction_id": transaction_id, "error": str(exc)},
        ) from exc

    return {
        "ok": True,
        "operation": "mutate",
        "action": "apply",
        "status": "APPLIED",
        "transaction_id": transaction_id,
        "base_head": current_head,
        "changed_files": changed_files,
        "before_hashes": before_hashes,
        "after_hashes": after_hashes,
        "syntax_preflight": syntax_preflight,
        "diff": "".join(diffs),
        "concurrency": {
            "global_head_guard": "strict" if expected_head is not None else "not_requested",
            "target_guards": "sha256",
            "commit_phase_lock": True,
            "final_compare_before_write": True,
        },
        "commit_created": False,
    }


def rollback_mutation(workspace_root: str, transaction_id: str) -> dict[str, Any]:
    ws = Workspace(workspace_root)
    manifest_path, manifest = _load_manifest(ws, transaction_id)
    changed_files = list(manifest.get("changed_files") or [])
    after_hashes = dict(manifest.get("after_hashes") or {})

    with ws.mutation_lock():
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
            backup = manifest_path.parent / "before" / path
            if not backup.is_file():
                raise BananaMeError("ROLLBACK_BACKUP_MISSING", f"Backup missing for {path}", recoverable=False)
            current = ws.read_text(path)
            expected = after_hashes.get(path)
            if expected and current.sha256 != expected:
                raise BananaMeError("ROLLBACK_CONFLICT", f"File changed during rollback: {path}")
            original = backup.read_bytes()
            ws.atomic_write(path, original, mode=current.mode)
            if "file_states" in manifest:
                manifest["file_states"][path] = "ROLLED_BACK"
                _write_manifest(ws, manifest_path, manifest)

        manifest["status"] = "ROLLED_BACK"
        _write_manifest(ws, manifest_path, manifest)

    return {
        "ok": True,
        "operation": "mutate",
        "action": "rollback",
        "status": "ROLLED_BACK",
        "transaction_id": transaction_id,
        "changed_files": changed_files,
    }



def _upgrade_legacy_manifest(ws: Workspace, manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Best-effort upgrade for an interrupted v0.1 transaction/1 journal.

    v0.1 persisted before-images and the edit list before source writes but only
    populated after_hashes after all writes completed. Reconstruct the intended
    post-image using the exact v0.1 sequential semantics so recovery can classify
    current files without guessing.
    """
    if manifest.get("schema") != "bananame-transaction/1":
        return manifest
    changed_files = list(manifest.get("changed_files") or [])
    edits = list(manifest.get("edits") or [])
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edit in edits:
        path = str(edit.get("path", "")).replace("\\", "/")
        if path:
            grouped[path].append(edit)
    after_hashes: dict[str, str] = {}
    for path in changed_files:
        backup = manifest_path.parent / "before" / path
        if not backup.is_file():
            raise BananaMeError("ROLLBACK_BACKUP_MISSING", f"Backup missing for {path}", recoverable=False)
        raw = backup.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BananaMeError("LEGACY_TRANSACTION_NOT_RECOVERABLE", f"Legacy backup is not UTF-8: {path}", recoverable=False) from exc
        newline = "\r\n" if b"\r\n" in raw else "\n"
        current = text
        for edit in grouped.get(path, []):
            search = _newline_adapt(str(edit.get("search", "")), newline)
            replace = _newline_adapt(str(edit.get("replace", "")), newline)
            if not search or current.count(search) != 1:
                raise BananaMeError(
                    "LEGACY_TRANSACTION_NOT_RECOVERABLE",
                    f"Cannot deterministically reconstruct legacy post-image for {path}.",
                    recoverable=False,
                )
            current = current.replace(search, replace, 1)
        after_hashes[path] = sha256_bytes(current.encode("utf-8"))
    manifest["schema"] = "bananame-transaction/2"
    manifest["after_hashes"] = after_hashes
    manifest["file_states"] = {path: "UNKNOWN" for path in changed_files}
    manifest["upgraded_from"] = "bananame-transaction/1"
    _write_manifest(ws, manifest_path, manifest)
    return manifest

def recover_mutation(workspace_root: str, transaction_id: str) -> dict[str, Any]:
    """Recover a v2 journal after process death. Mixed states are rolled back to the before-image."""
    ws = Workspace(workspace_root)
    manifest_path, manifest = _load_manifest(ws, transaction_id)
    if manifest.get("schema") == "bananame-transaction/1":
        manifest = _upgrade_legacy_manifest(ws, manifest_path, manifest)
    if manifest.get("schema") != "bananame-transaction/2":
        raise BananaMeError(
            "TRANSACTION_SCHEMA_UNSUPPORTED",
            "Automatic recovery requires a supported BananaMe transaction journal.",
            recoverable=False,
        )
    changed_files = list(manifest.get("changed_files") or [])
    before_hashes = dict(manifest.get("before_hashes") or {})
    after_hashes = dict(manifest.get("after_hashes") or {})

    with ws.mutation_lock():
        observed: dict[str, str] = {}
        conflicts: list[dict[str, str]] = []
        for path in changed_files:
            snap = ws.read_text(path)
            if snap.sha256 == before_hashes.get(path):
                observed[path] = "BEFORE"
            elif snap.sha256 == after_hashes.get(path):
                observed[path] = "AFTER"
            else:
                conflicts.append({"path": path, "actual_sha256": snap.sha256})
        if conflicts:
            manifest["status"] = "RECOVERY_REQUIRED"
            manifest["recovery_conflicts"] = conflicts
            _write_manifest(ws, manifest_path, manifest)
            raise BananaMeError(
                "RECOVERY_CONFLICT",
                "Recovery refused because one or more files match neither journaled before nor after state.",
                recoverable=False,
                details={"transaction_id": transaction_id, "conflicts": conflicts},
            )

        states = set(observed.values())
        if states == {"AFTER"}:
            manifest["status"] = "APPLIED_RECOVERED"
            manifest["file_states"] = {path: "APPLIED" for path in changed_files}
            _write_manifest(ws, manifest_path, manifest)
            return {
                "ok": True,
                "operation": "mutate",
                "action": "recover",
                "status": "APPLIED_RECOVERED",
                "transaction_id": transaction_id,
                "changed_files": changed_files,
            }

        manifest["status"] = "RECOVERING"
        _write_manifest(ws, manifest_path, manifest)
        for path in changed_files:
            if observed[path] == "BEFORE":
                continue
            current = ws.read_text(path)
            if current.sha256 != after_hashes[path]:
                raise BananaMeError("RECOVERY_CONFLICT", f"File changed during recovery: {path}", recoverable=False)
            backup = manifest_path.parent / "before" / path
            if not backup.is_file():
                raise BananaMeError("ROLLBACK_BACKUP_MISSING", f"Backup missing for {path}", recoverable=False)
            ws.atomic_write(path, backup.read_bytes(), mode=current.mode)
            manifest["file_states"][path] = "ROLLED_BACK"
            _write_manifest(ws, manifest_path, manifest)

        manifest["status"] = "ROLLED_BACK_RECOVERED"
        _write_manifest(ws, manifest_path, manifest)
        return {
            "ok": True,
            "operation": "mutate",
            "action": "recover",
            "status": "ROLLED_BACK_RECOVERED",
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
    if action == "recover":
        if not transaction_id:
            raise BananaMeError("TRANSACTION_ID_REQUIRED", "recover requires transaction_id")
        return recover_mutation(workspace_root, transaction_id)
    raise BananaMeError("INVALID_MUTATION_ACTION", "action must be 'apply', 'rollback' or 'recover'")
