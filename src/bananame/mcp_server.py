from __future__ import annotations

import os
from typing import Any

try:
    from mcp.server import MCPServer
except ImportError as exc:  # pragma: no cover - optional dependency
    raise RuntimeError("Install BananaMe with the 'mcp' extra: pip install 'bananame-code[mcp]'") from exc

from . import __version__
from .binding import mcp_workspace_root
from .core import safe_call
from .mutate import mutate as mutate_core
from .understand import understand as understand_core
from .verify import verify as verify_core

mcp = MCPServer(
    "BananaMe",
    description="Headless AI-to-AI code interface for deterministic repository understanding, mutation and verification.",
    instructions=(
        "BananaMe exposes exactly three agent operations: understand, mutate, verify. "
        "It contains no planner, LLM, memory system or governance layer. Use understand before mutation to obtain current file hashes. "
        "mutate requires exact SEARCH/REPLACE blocks guarded by the file SHA-256 and optionally the Git HEAD. "
        "The MCP host binds one workspace through BANANAME_WORKSPACE_ROOT; the agent cannot select an arbitrary filesystem root. "
        "Mutations use target hashes, a short commit-phase lock and crash-recovery journals. A mutation is not a commit or proof of correctness. Call verify after mutation. "
        "Promotion, commit, deployment and independent assurance belong to the host/control plane."
    ),
    version=__version__,
)


@mcp.tool()
def understand(
    query: str = "",
    hot_files: list[str] | None = None,
    max_context_bytes: int = 8192,
    max_results: int = 20,
) -> dict[str, Any]:
    """Return compact, structured repository evidence without modifying the workspace."""
    return safe_call(
        lambda: understand_core(
            mcp_workspace_root(),
            query=query,
            hot_files=hot_files,
            max_context_bytes=max_context_bytes,
            max_results=max_results,
        )
    )


@mcp.tool()
def mutate(
    edits: list[dict[str, str]] | None = None,
    expected_head: str | None = None,
    action: str = "apply",
    transaction_id: str | None = None,
) -> dict[str, Any]:
    """Apply, rollback or recover a guarded journaled SEARCH/REPLACE mutation. Never commits."""
    return safe_call(
        lambda: mutate_core(
            mcp_workspace_root(),
            edits=edits,
            expected_head=expected_head,
            action=action,
            transaction_id=transaction_id,
        )
    )


@mcp.tool()
def verify(
    paths: list[str] | None = None,
    transaction_id: str | None = None,
    commands: list[list[str]] | None = None,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    """Verify syntax and explicit argv-based commands and return machine-readable evidence."""
    return safe_call(
        lambda: verify_core(
            mcp_workspace_root(),
            paths=paths,
            transaction_id=transaction_id,
            commands=commands,
            timeout_seconds=timeout_seconds,
        )
    )


def main() -> None:
    transport = os.environ.get("BANANAME_MCP_TRANSPORT", "stdio")
    kwargs: dict[str, Any] = {}
    if transport in {"streamable-http", "sse"}:
        kwargs["host"] = os.environ.get("BANANAME_MCP_HOST", "127.0.0.1")
        kwargs["port"] = int(os.environ.get("BANANAME_MCP_PORT", "8011"))
    mcp.run(transport=transport, **kwargs)


if __name__ == "__main__":
    main()
