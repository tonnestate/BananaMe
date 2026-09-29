from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from .errors import BananaMeError


def mcp_workspace_root(environ: Mapping[str, str] | None = None) -> str:
    """Return the host-bound MCP workspace.

    The agent-facing MCP schema intentionally does not accept an arbitrary
    workspace path. The host binds one workspace when it starts the server.
    """
    env = os.environ if environ is None else environ
    raw = env.get("BANANAME_WORKSPACE_ROOT", "").strip()
    if not raw:
        raise BananaMeError(
            "MCP_WORKSPACE_REQUIRED",
            "Set BANANAME_WORKSPACE_ROOT before starting the BananaMe MCP server.",
            recoverable=False,
        )
    path = Path(raw).expanduser().resolve()
    if not path.is_dir():
        raise BananaMeError(
            "MCP_WORKSPACE_NOT_FOUND",
            f"Configured BananaMe MCP workspace does not exist: {path}",
            recoverable=False,
        )
    return str(path)
