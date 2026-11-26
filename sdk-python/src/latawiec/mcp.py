"""MCP server for coding agents: inspect and preview Latawiec apps without a phone.

Run `latawiec-mcp` (stdio transport) from the directory that holds the app modules;
it needs the `mcp` extra (`pip install latawiec[mcp]`).
"""

from __future__ import annotations

import importlib
import json
import os
import sys

from mcp.server.mcpserver import MCPServer

import latawiec
from latawiec.server import Latawiec

server = MCPServer("latawiec")


def _load_app(module: str) -> Latawiec:
    # Reload a cached module, or an agent editing the app would keep getting
    # the pre-edit screens for the rest of the MCP session.
    cached = sys.modules.get(module)
    mod = importlib.reload(cached) if cached else importlib.import_module(module)
    for value in vars(mod).values():
        if isinstance(value, Latawiec):
            return value
    raise ValueError(f"module {module!r} defines no Latawiec app")


# The page belongs to the package; this registers it as a tool, name and
# description included, rather than restating it here.
reference = server.tool()(latawiec.reference)


@server.tool()
def list_screens(module: str) -> list[str]:
    """List the screens a Latawiec app module registers (e.g. module='examples.hello')."""
    return list(_load_app(module).screen_names)


@server.tool()
def render_screen(module: str, screen: str) -> str:
    """Render one screen of a Latawiec app module to its DivKit card JSON.

    Needs no server and no phone; fails loudly when the module has no such
    screen or the screen builder raises.
    """
    return json.dumps(_load_app(module).render_screen(screen), indent=2)


def main() -> None:
    # Console scripts do not get the working directory on sys.path, and app
    # modules are addressed relative to it.
    sys.path.insert(0, os.getcwd())
    server.run()
