from __future__ import annotations

import subprocess
from pathlib import Path


def _run(root: Path, args: list[str], timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def head_revision(root: Path) -> str | None:
    result = _run(root, ["rev-parse", "HEAD"])
    return result.stdout.strip() if result.returncode == 0 else None


def working_tree_dirty(root: Path) -> bool | None:
    result = _run(root, ["status", "--porcelain=v1", "--untracked-files=normal"])
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def tracked_and_untracked_files(root: Path) -> list[str]:
    result = _run(root, ["ls-files", "-co", "--exclude-standard"])
    if result.returncode != 0:
        return []
    return sorted({line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()})


def cochange(root: Path, anchor_paths: list[str], *, commit_limit: int = 200, result_limit: int = 12) -> list[dict]:
    if not anchor_paths:
        return []
    result = _run(root, ["log", f"-n{max(1, min(commit_limit, 1000))}", "--format=@@%H", "--name-only"], timeout=20.0)
    if result.returncode != 0:
        return []
    anchors = {p.replace("\\", "/") for p in anchor_paths}
    counts: dict[str, int] = {}
    current: list[str] = []

    def flush() -> None:
        if not current or not anchors.intersection(current):
            return
        for path in set(current):
            if path not in anchors:
                counts[path] = counts.get(path, 0) + 1

    for raw in result.stdout.splitlines():
        line = raw.strip()
        if line.startswith("@@"):
            flush()
            current = []
        elif line:
            current.append(line.replace("\\", "/"))
    flush()
    return [
        {"path": path, "cochange_commits": count}
        for path, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:result_limit]
    ]
