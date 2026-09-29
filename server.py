"""Convenience entry point for BananaMe MCP development and stdio execution."""

from bananame.mcp_server import mcp, main

__all__ = ["mcp"]

if __name__ == "__main__":
    main()
