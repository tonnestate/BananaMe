from pathlib import Path

import pytest

from bananame.binding import mcp_workspace_root
from bananame.errors import BananaMeError


def test_mcp_workspace_must_be_host_bound(tmp_path: Path) -> None:
    with pytest.raises(BananaMeError) as exc:
        mcp_workspace_root({})
    assert exc.value.code == "MCP_WORKSPACE_REQUIRED"


def test_mcp_workspace_binding_resolves_existing_directory(tmp_path: Path) -> None:
    nested = tmp_path / "repo"
    nested.mkdir()
    assert mcp_workspace_root({"BANANAME_WORKSPACE_ROOT": str(nested)}) == str(nested.resolve())


def test_mcp_workspace_binding_rejects_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(BananaMeError) as exc:
        mcp_workspace_root({"BANANAME_WORKSPACE_ROOT": str(tmp_path / "missing")})
    assert exc.value.code == "MCP_WORKSPACE_NOT_FOUND"
