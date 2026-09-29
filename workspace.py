from __future__ import annotations

import hashlib
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

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


def _fsync_directory(path: Path) -> None:
    """Best-effort directory fsync after rename/replace on platforms that support it."""
    if os.name == "nt":
        return
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _mkdirs_durable(path: Path) -> None:
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(exist_ok=True)
        _fsync_directory(directory.parent)


def _atomic_replace(path: Path, raw: bytes, *, mode: int | None = None) -> None:
    _mkdirs_durable(path.parent)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.bananame-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


class Workspace:
    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise BananaMeError("WORKSPACE_NOT_FOUND", f"Workspace does not exist: {self.root}")

    def _internal_root(self) -> Path:
        base = self.root / ".bananame"
        if base.exists() and base.is_symlink():
            raise BananaMeError(
                "INTERNAL_SYMLINK_DENIED",
                ".bananame must be a real directory inside the workspace, not a symlink.",
                recoverable=False,
            )
        _mkdirs_durable(base)
        if not base.is_dir():
            raise BananaMeError("INTERNAL_PATH_INVALID", ".bananame is not a directory.", recoverable=False)
        return base

    def _validate_internal_path(self, path: Path) -> Path:
        base = self._internal_root()
        try:
            lexical = path.relative_to(base) if path.is_absolute() else path
        except ValueError as exc:
            raise BananaMeError("INTERNAL_PATH_ESCAPE", "Internal path escapes .bananame.", recoverable=False) from exc
        candidate = base / lexical if not path.is_absolute() else path
        current = base
        for part in candidate.relative_to(base).parts:
            current = current / part
            if current.exists() and current.is_symlink():
                raise BananaMeError(
                    "INTERNAL_SYMLINK_DENIED",
                    f"Symlink inside .bananame is not allowed: {current.relative_to(base)}",
                    recoverable=False,
                )
        try:
            candidate.resolve(strict=False).relative_to(base.resolve(strict=False))
        except ValueError as exc:
            raise BananaMeError("INTERNAL_PATH_ESCAPE", "Internal path escapes .bananame.", recoverable=False) from exc
        return candidate

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
        _atomic_replace(self.resolve(relative_path), raw, mode=mode)

    def atomic_write_internal(self, path: Path, raw: bytes, *, mode: int | None = None) -> None:
        safe = self._validate_internal_path(path)
        _atomic_replace(safe, raw, mode=mode)

    def internal_dir(self, *parts: str) -> Path:
        base = self._internal_root()
        path = base.joinpath(*parts)
        safe = self._validate_internal_path(path)
        _mkdirs_durable(safe)
        self._validate_internal_path(safe)
        return safe

    @contextmanager
    def mutation_lock(self) -> Iterator[None]:
        """Short-lived cross-process commit-phase lock. It is released automatically on process death."""
        lock_dir = self.internal_dir("locks")
        lock_path = lock_dir / "mutation.lock"
        if lock_path.exists() and lock_path.is_symlink():
            raise BananaMeError(
                "INTERNAL_SYMLINK_DENIED",
                "BananaMe mutation lock must not be a symlink.",
                recoverable=False,
            )
        handle = open(lock_path, "a+b")
        try:
            if lock_path.stat().st_size == 0:
                handle.write(b"0")
                handle.flush()
                os.fsync(handle.fileno())
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise BananaMeError(
                    "MUTATION_BUSY",
                    "Another BananaMe mutation or recovery currently owns the workspace commit phase.",
                    details={"lock": str(lock_path)},
                ) from exc
            try:
                yield
            finally:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            handle.close()
