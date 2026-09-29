from __future__ import annotations

from typing import Any, Callable

from .errors import BananaMeError
from .mutate import mutate
from .understand import understand
from .verify import verify


def safe_call(fn: Callable[..., dict[str, Any]], /, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except BananaMeError as exc:
        return {"ok": False, "error": exc.as_dict()}
    except Exception as exc:  # keep MCP/CLI machine-readable without hiding the failure class
        return {
            "ok": False,
            "error": {
                "code": "UNEXPECTED_ERROR",
                "message": str(exc),
                "recoverable": False,
                "details": {"type": type(exc).__name__},
            },
        }


class BananaMe:
    """Three-operation headless code interface for agents."""

    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root

    def understand(self, **kwargs: Any) -> dict[str, Any]:
        return safe_call(understand, self.workspace_root, **kwargs)

    def mutate(self, **kwargs: Any) -> dict[str, Any]:
        return safe_call(mutate, self.workspace_root, **kwargs)

    def verify(self, **kwargs: Any) -> dict[str, Any]:
        return safe_call(verify, self.workspace_root, **kwargs)
