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
  # text is shown as written, "@{...}" included; Text(Expression("Hello, @{name}!"))
  # asks for a DivKit expression instead; weight: "light" |
  # "regular" | "medium" | "bold"; align: "left" | "center" | "right"
- Image(url)
- Button(label, on_tap=..., color="#2962FF", text_color="#FFFFFF")
  # on_tap: Navigate(screen) | SetVariable(variable, value)
  #       | Submit(action, send=(variable, ...))
  #       | SignOut(screen=None)  # drops the token AND the screen cache,
  #         lands on `screen`, the manifest's login screen, or "home"
  #       | Share(text) | OpenUrl(url) | CopyToClipboard(text)
  #       | Haptic(feedback="light"|"medium"|"heavy"|"success"|"error")
  #       | RequestLocation(variable, then=None)  # see below
  #       | Purchase(product, action)  # see below
  #       | Unlock(action, send=(variable, ...), reason="Confirm it's you")
  #       | a tuple of the above, run in order: (Haptic("success"), Submit(...))
  # OpenUrl leaves the app; shells follow http(s), mailto, tel, and sms only
- TextInput(variable, hint=None, initial="", password=False)  # declares its variable
- Switch(variable, initial=False)  # boolean variable
- Select(variable, options=("S", Option("Medium", "m")), hint=None, initial="")
  # options: strings, or Option(label, value) when they differ
- Slider(variable, min=0, max=100, initial=None, color="#2962FF")  # integer variable
- ImagePicker(variable, label=None, height=160, style=None, source="gallery")
  # tap opens the system gallery, or the camera with source="camera"; the
  # shell uploads the result to the app's @app.upload handler and sets
  # `variable` to its return value (typically a URL), which the component
  # previews and a Submit(send=(variable,)) forwards. The label defaults to
  # the source ("Choose a photo" / "Take a photo"). source="camera" costs no
  # Android permission; a device with no camera, or one whose owner turned
  # camera access off, says so rather than falling back to the gallery
- Column(*children), Row(*children), Stack(*children)  # Stack overlaps; place
  children with Style align/align_vertical
- Gallery(*children, horizontal=False, spacing=None)  # scrolling list
- LoadMore(action)  # pagination sentinel, last child of a Gallery
- Map(latitude, longitude, zoom=14, height=240, markers=(Marker(lat, lon,
  label), ...), tiles=None)  # pan and zoom; each shell draws it with what
  the platform has (MapKit on iOS, a tile view on Android), so it costs no
  dependency and no API key and the two look different by default; `tiles`
  is an XYZ template ("https://host/{z}/{x}/{y}.png") both shells then draw
  instead, and has to be an http(s) URL carrying all three placeholders.
  The Android fallback is OpenStreetMap's own server, a courtesy
  with a usage policy — ship a real app pointing at your own
- Grid(*children, columns=N)  # fixed columns, row by row
- Pager(*children, id=None, spacing=None) + Indicator(pager=id)  # swipeable
  pages with dots
- Tabs(("Title", component), ...)  # in-screen tabs; the native bottom bar is
  Latawiec(tabs=[...])
- Video(url, autoplay=False, loop=False, muted=False, height=200)  # the
  platform player: MP4 and HLS. DASH needs an Android shell built with
  -PwithVideo (docs/shipping.md); iOS needs no flag
- GifImage(url)
  # Video plays through the platform player on both shells (AVPlayer /
  # MediaPlayer): MP4 and HLS, not DASH/DRM — those need a custom factory
- Separator(color="#B0BEC5"), Spacer(height=N) or Spacer(width=N)
- render(component) -> DivKit card dict (what a shell consumes)

Variables bound by controls are hoisted to the card, so any component can read
them, through an Expression: Text(Expression("@{dark}")),
Text(Expression("Size: @{size}")). A plain string is shown as typed, so a name or
a review someone else wrote is never read as an expression. Submit sends string
variables.
Every name in a send= has to be declared somewhere on the same screen — by a
control, or by a SetVariable/RequestLocation on it — or render() refuses the
screen: DivKit evaluates the action's URL at tap time, and an undeclared name
makes that evaluation fail, leaving a button that silently does nothing.

Styling — every component takes style=Style(...):
- Style(padding, margin, width, height, background, corner_radius, border,
  align, align_vertical, alpha, appear, disappear, move)
- padding/margin: int for all sides, or Edges(top, right, bottom, left)
- width/height: dp as int, or "fill" / "wrap"
- background/border: "#RRGGBB" color; align places the component in its parent
- appear/disappear: Fade(duration=300, delay=0) | Slide(edge="bottom", ...) |
  Grow(...) — how the component enters and leaves, also on live refreshes
  (a streamed chat bubble fades in); move=N animates layout shifts over N ms
- Button(..., tap_animation="fade" | "scale" | "none") tunes press feedback

App and server (Latawiec subclasses FastAPI):
    import latawiec as lt

    app = lt.Latawiec()

    @app.screen("home")
    def home() -> lt.Component:
        return lt.Column(lt.Text("Hello", size=28))

    @app.screen("product/{id}")              # {placeholders} capture path params
    def product(ctx: lt.Context) -> lt.Component:
        return lt.Column(lt.Text(ctx.params["id"]))  # Navigate(f"product/{slug}")
  # Exact names beat templates, and the most-literal template wins. Two
  # same-shape templates that can claim one path ("{a}/edit" + "product/{id}")
  # raise ValueError at registration — rename a segment instead.
- ctx also carries what the shell reports: ctx.locale ("pl-PL"), ctx.platform
  ("android"/"ios"), ctx.timezone ("Europe/Warsaw"), ctx.app_version — all ""
  when unknown. i18n is a plain `if ctx.locale.startswith("pl")` server-side.

- Builders, action handlers, and the auth check may be sync or `async def`;
  sync ones run in a threadpool, so blocking calls (a database read) are fine.
- GET /screens/{name} returns the rendered card JSON; unknown names 404.
- WS /ws/screens/{name} sends the card on connect and holds the socket.
- @app.action(name) registers a Submit handler: it gets the submitted values
  as dict[str, str] and may return Navigate to send the shell onward.
- @app.screen(..., refreshable=True) adds the pull-to-refresh gesture in
  production (on iOS the screen's root must scroll, e.g. a Gallery).
- Purchase(product, action) runs the store's buy flow and submits `action`
  with the store's receipt under "receipt" and the id under "product".
  Verify that receipt with Apple or Google in the handler before granting
  anything: the shell reports what the store said, and a patched client can
  report anything. A cancelled purchase submits nothing. iOS needs no build
  flag; Android needs -PwithBilling (docs/shipping.md), and a build without
  it says so instead of leaving a silent button.
- Unlock(action, send=(), reason=...) puts the device's own check — a
  fingerprint, a face, or the passcode — in front of a Submit: the action
  POSTs, with the same values Submit would send, only once the check
  passes, and the handler may answer with a Navigate. It gates the tap,
  not the server: nothing stops a patched client from POSTing the action
  anyway, so anything that must not happen for the wrong person still
  needs @app.auth and a check in the handler. A device with no lock set
  up says "This device has no lock set up" on both shells and submits
  nothing; a cancel submits nothing silently.
- RequestLocation(variable, then=None) asks the device where it is and puts
  "lat,lon" in `variable`, which it declares itself. The first tap raises the
  system permission prompt, so put it on a control the user pressed on
  purpose. A denial, or no fix within ten seconds, leaves the variable empty
  — render the fallback the screen wants. `then` names an action to submit
  once the answer is in, carrying the variable; pairing RequestLocation with
  a Submit in a tuple instead would fire it before the fix arrives.
- LoadMore(action, label="Loading more…") is the infinite-scroll sentinel:
  last in a Gallery, it submits `action` when scrolled into view; the handler
  extends the data and calls app.refresh(), so pair it with live=True, and
  render it only while there is more.
- @app.screen(..., live=True) keeps the screen subscribed in production;
  app.refresh(name) re-renders it for every phone showing it (per-user ctx) —
  refresh fast and that is streaming. @app.screen(..., refresh=N) is the
  cheap variant: the shell refetches every N seconds while on display.
  refresh() reaches this process only: a second instance serves phones it
  never touches, so run one instance or refresh every instance off a shared
  bus (docs/shipping.md). `name` is the template as registered, so a routed
  screen takes "chat/{room}", not "chat/42", and pushes to every room.
- @app.upload registers the file sink: it gets an Upload(name, content_type,
  data: bytes) plus optional ctx and returns the string the picker's variable
  is set to. Respects @app.auth; bodies over max_upload_mb (Latawiec arg,
  default 10) answer 413.
- @app.device registers the push-token sink (token, optional ctx) and turns
  push on; a push message's data "screen" key opens that screen on tap.
  Sending is the app's job (its own FCM/APNs credentials); docs/shipping.md
  has the payload shapes.
- Latawiec(tabs=[Tab(screen, title, icon=None)], theme=Theme(accent="#2962FF"),
  login=None, version=None, dev=True, app_links=None) declares the native
  bottom bar, chrome colors, the screen shown on 401, the content version (a
  change tells shells to drop cached screens), and dev mode (deploy with
  dev=False: shells then fetch screens over GET and cache them); shells read
  GET /manifest. app.tabs/theme/login may be reassigned at runtime: a
  fingerprint on every response lets the shells pick the new chrome up
  mid-session (add a tab from a handler and the bar rebuilds, no restart).
  app_links=AppLinks(android_package, android_fingerprints,
  ios_app_id) makes the server serve both /.well-known ownership files, so
  https links open the app (App Links / Universal Links).
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
