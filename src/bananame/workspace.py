from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .errors import BananaMeError


@dataclass(frozen=True)
class TextSnapshot:
    path: str
    text: str
    raw: bytes
    sha256: str
    newline: str
    mode: int


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Workspace:
    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise BananaMeError("WORKSPACE_NOT_FOUND", f"Workspace does not exist: {self.root}")

    def resolve(self, relative_path: str, *, allow_internal: bool = False) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise BananaMeError("ABSOLUTE_PATH_DENIED", "Only workspace-relative paths are accepted.")
        lexical = self.root / candidate
        resolved = lexical.resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise BananaMeError("PATH_ESCAPE", f"Path escapes workspace: {relative_path}") from exc
        parts = candidate.parts
        if ".git" in parts:
            raise BananaMeError("GIT_INTERNAL_DENIED", "Direct mutation of .git is not allowed.")
        if not allow_internal and ".bananame" in parts:
            raise BananaMeError("INTERNAL_PATH_DENIED", "Direct access to .bananame is reserved for BananaMe.")
        return resolved

    def read_text(self, relative_path: str) -> TextSnapshot:
        lexical = self.root / Path(relative_path)
        if lexical.is_symlink():
            raise BananaMeError("SYMLINK_FILE_DENIED", f"Symlink files are not mutable in v0.1: {relative_path}")
        path = self.resolve(relative_path)
        if not path.is_file():
            raise BananaMeError("FILE_NOT_FOUND", f"File not found: {relative_path}")
        raw = path.read_bytes()
        if b"\x00" in raw:
            raise BananaMeError("BINARY_FILE_UNSUPPORTED", f"Binary file is not supported: {relative_path}")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BananaMeError("UTF8_REQUIRED", f"File is not UTF-8: {relative_path}") from exc
        newline = "\r\n" if b"\r\n" in raw else "\n"
        return TextSnapshot(
            path=relative_path.replace("\\", "/"),
            text=text,
            raw=raw,
            sha256=sha256_bytes(raw),
            newline=newline,
            mode=path.stat().st_mode,
        )

    def atomic_write(self, relative_path: str, raw: bytes, *, mode: int | None = None) -> None:
        path = self.resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.bananame-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            if mode is not None:
                os.chmod(tmp_name, mode)
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def internal_dir(self, *parts: str) -> Path:
        base = self.root / ".bananame"
        base.mkdir(exist_ok=True)
        path = base.joinpath(*parts)
        path.mkdir(parents=True, exist_ok=True)
        return path
