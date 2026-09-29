from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .errors import BananaMeError
from .workspace import Workspace


def syntax_check_text(path: str, text: str) -> dict[str, Any]:
    suffix = Path(path).suffix.lower()
    try:
        if suffix == ".py":
            compile(text, path, "exec")
            return {"path": path, "status": "PASS", "checker": "python.compile"}
        if suffix == ".json":
            json.loads(text)
            return {"path": path, "status": "PASS", "checker": "json.loads"}
        if suffix == ".toml":
            tomllib.loads(text)
            return {"path": path, "status": "PASS", "checker": "tomllib.loads"}
        if suffix in {".xml", ".svg"}:
            ET.fromstring(text)
            return {"path": path, "status": "PASS", "checker": "xml.etree"}
    except Exception as exc:
        return {"path": path, "status": "FAIL", "checker": "builtin", "error": str(exc)}
    return {"path": path, "status": "SKIP", "checker": "none"}


def _external_syntax(ws: Workspace, path: str) -> dict[str, Any] | None:
    suffix = Path(path).suffix.lower()
    command: list[str] | None = None
    checker = ""
    if suffix in {".js", ".mjs", ".cjs"} and shutil.which("node"):
        command, checker = ["node", "--check", path], "node --check"
    elif suffix == ".php" and shutil.which("php"):
        command, checker = ["php", "-l", path], "php -l"
    elif suffix in {".sh", ".bash"} and shutil.which("bash"):
        command, checker = ["bash", "-n", path], "bash -n"
    if not command:
        return None
    result = subprocess.run(command, cwd=ws.root, capture_output=True, text=True, timeout=20, check=False)
    return {
        "path": path,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "checker": checker,
        "exit_code": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def _load_transaction_paths(ws: Workspace, transaction_id: str) -> list[str]:
    manifest = ws.root / ".bananame" / "transactions" / transaction_id / "manifest.json"
    if not manifest.is_file():
        raise BananaMeError("TRANSACTION_NOT_FOUND", f"Unknown transaction: {transaction_id}")
    data = json.loads(manifest.read_text("utf-8"))
    return list(data.get("changed_files") or [])


def verify(
    workspace_root: str,
    paths: list[str] | None = None,
    transaction_id: str | None = None,
    commands: list[list[str]] | None = None,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    ws = Workspace(workspace_root)
    selected = list(paths or [])
    if transaction_id:
        for path in _load_transaction_paths(ws, transaction_id):
            if path not in selected:
                selected.append(path)
    timeout_seconds = max(1, min(int(timeout_seconds), 900))

    syntax: list[dict[str, Any]] = []
    for rel in selected:
        snap = ws.read_text(rel)
        built = syntax_check_text(rel, snap.text)
        external = None if built["status"] == "FAIL" else _external_syntax(ws, rel)
        syntax.append(external or built)

    command_results: list[dict[str, Any]] = []
    for command in commands or []:
        if not isinstance(command, list) or not command or not all(isinstance(part, str) and part for part in command):
            raise BananaMeError("INVALID_COMMAND", "Verification commands must be non-empty argv arrays; shell strings are not accepted.")
        executable = shutil.which(command[0])
        if executable is None:
            command_results.append({"argv": command, "status": "FAIL", "error": "COMMAND_NOT_FOUND"})
            continue
        env = os.environ.copy()
        env.pop("GIT_DIR", None)
        env.pop("GIT_WORK_TREE", None)
        try:
            result = subprocess.run(
                [executable, *command[1:]],
                cwd=ws.root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                env=env,
            )
            command_results.append({
                "argv": command,
                "status": "PASS" if result.returncode == 0 else "FAIL",
                "exit_code": result.returncode,
                "stdout": result.stdout[-12000:],
                "stderr": result.stderr[-12000:],
            })
        except subprocess.TimeoutExpired as exc:
            command_results.append({
                "argv": command,
                "status": "FAIL",
                "error": "TIMEOUT",
                "timeout_seconds": timeout_seconds,
                "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
                "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            })

    failures = [item for item in syntax if item.get("status") == "FAIL"] + [
        item for item in command_results if item.get("status") == "FAIL"
    ]
    return {
        "ok": not failures,
        "operation": "verify",
        "transaction_id": transaction_id,
        "paths": selected,
        "syntax": syntax,
        "commands": command_results,
        "status": "VERIFIED" if not failures else "VERIFICATION_FAILED",
        "failure_count": len(failures),
    }
