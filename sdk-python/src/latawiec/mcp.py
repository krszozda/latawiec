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

from latawiec.server import Latawiec

server = MCPServer("latawiec")

REFERENCE = """\
Latawiec: write native mobile screens in Python; a thin native shell renders them
with DivKit. Package `latawiec` on PyPI.

Components:
- Text(text, size=None, color=None, weight=None, align=None, line_height=None)
  # text may use DivKit expressions: Text("Hello, @{name}!"); weight: "light" |
  # "regular" | "medium" | "bold"; align: "left" | "center" | "right"
- Image(url)
- Button(label, on_tap=..., color="#2962FF", text_color="#FFFFFF")
  # on_tap: Navigate(screen) | SetVariable(variable, value)
  #       | Submit(action, send=(variable, ...))
  #       | Share(text) | OpenUrl(url) | CopyToClipboard(text)
  #       | Haptic(feedback="light"|"medium"|"heavy"|"success"|"error")
  #       | a tuple of the above, run in order: (Haptic("success"), Submit(...))
  # OpenUrl leaves the app; shells follow http(s), mailto, tel, and sms only
- TextInput(variable, hint=None, initial="", password=False)  # declares its variable
- Switch(variable, initial=False)  # boolean variable
- Select(variable, options=("S", Option("Medium", "m")), hint=None, initial="")
  # options: strings, or Option(label, value) when they differ
- Slider(variable, min=0, max=100, initial=None, color="#2962FF")  # integer variable
- Column(*children), Row(*children), Stack(*children)  # Stack overlaps; place
  children with Style align/align_vertical
- Gallery(*children, horizontal=False, spacing=None)  # scrolling list
- Grid(*children, columns=N)  # fixed columns, row by row
- Pager(*children, id=None, spacing=None) + Indicator(pager=id)  # swipeable
  pages with dots
- Tabs(("Title", component), ...)  # in-screen tabs; the native bottom bar is
  Latawiec(tabs=[...])
- Video(url, autoplay=False, loop=False, muted=False), GifImage(url)
  # Video plays on iOS out of the box; the Android shell ships no player yet
  # (a bundled player would blow the APK size budget) and shows an empty area
- Separator(color="#B0BEC5"), Spacer(height=N) or Spacer(width=N)
- render(component) -> DivKit card dict (what a shell consumes)

Variables bound by controls are hoisted to the card, so any component can read
them: Text("@{dark}"), Text("Size: @{size}"). Submit sends string variables.

Styling — every component takes style=Style(...):
- Style(padding, margin, width, height, background, corner_radius, border,
  align, align_vertical, alpha)
- padding/margin: int for all sides, or Edges(top, right, bottom, left)
- width/height: dp as int, or "fill" / "wrap"
- background/border: "#RRGGBB" color; align places the component in its parent

App and server (Latawiec subclasses FastAPI):
    import latawiec as lt

    app = lt.Latawiec()

    @app.screen("home")
    def home() -> lt.Component:
        return lt.Column(lt.Text("Hello", size=28))

    @app.screen("product/{id}")              # {placeholders} capture path params
    def product(ctx: lt.Context) -> lt.Component:
        return lt.Column(lt.Text(ctx.params["id"]))  # Navigate(f"product/{slug}")
- ctx also carries what the shell reports: ctx.locale ("pl-PL"), ctx.platform
  ("android"/"ios"), ctx.timezone ("Europe/Warsaw"), ctx.app_version — all ""
  when unknown. i18n is a plain `if ctx.locale.startswith("pl")` server-side.

- Builders, action handlers, and the auth check may be sync or `async def`;
  sync ones run in a threadpool, so blocking calls (a database read) are fine.
- GET /screens/{name} returns the rendered card JSON; unknown names 404.
- WS /ws/screens/{name} sends the card on connect and holds the socket.
- @app.action(name) registers a Submit handler: it gets the submitted values
  as dict[str, str] and may return Navigate to send the shell onward.
- Latawiec(tabs=[Tab(screen, title, icon=None)], theme=Theme(accent="#2962FF"),
  login=None, version=None, dev=True) declares the native bottom bar, chrome
  colors, the screen shown on 401, the content version (a change tells shells
  to drop cached screens), and dev mode (deploy with dev=False: shells then
  fetch screens over GET and cache them); shells read GET /manifest.
- @app.screen(name, cache="static" | "swr" | "no-store") steers the shells'
  screen cache; guarded screens default to no-store, the rest to swr.
- app.assets("static") serves that directory under /assets — tab icons point
  there, e.g. Tab("home", "Home", icon="/assets/home.png").
- @app.auth registers the token check: it gets the bearer token (or None) and
  returns a truthy user object, or None to reject. Guarded screens/actions then
  need Authorization: Bearer <token>; register the login screen and its sign-in
  action with public=True. A sign-in handler returns Grant(token, screen) — the
  shell stores the token and navigates on. Builders may take a Context
  (ctx.user, ctx.params); action handlers may take it as a second argument.

Dev loop: `uvicorn module:app --host 0.0.0.0 --reload` — the native shells
(Android and iOS) reconnect on every save and live-reload the screen. System
back walks the shell's screen stack.
"""


def _load_app(module: str) -> Latawiec:
    # Reload a cached module, or an agent editing the app would keep getting
    # the pre-edit screens for the rest of the MCP session.
    cached = sys.modules.get(module)
    mod = importlib.reload(cached) if cached else importlib.import_module(module)
    for value in vars(mod).values():
        if isinstance(value, Latawiec):
            return value
    raise ValueError(f"module {module!r} defines no Latawiec app")


@server.tool()
def reference() -> str:
    """The Latawiec DSL on one page: components, actions, server, dev loop."""
    return REFERENCE


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
