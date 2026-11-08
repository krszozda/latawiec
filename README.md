# Latawiec

**Latawiec** (Polish for *kite*) — native mobile apps flown from a Python backend.

A kite flies in the sky, but the string stays in your hand. Latawiec works the same way:
screens are written in Python on your server, and a thin native shell on the phone renders
them natively with [DivKit](https://divkit.tech). Change the Python, and the app changes —
no app release, no Kotlin, no Swift.

```python
import latawiec as lt

app = lt.Latawiec()


@app.screen("home")
def home() -> lt.Component:
    return lt.Column(
        lt.Text("Hello from the server", size=24),
        lt.Button("Open checkout", on_tap=lt.Navigate("checkout")),
    )
```

`app` is a regular ASGI/FastAPI app — `uvicorn main:app` serves the rendered screen at
`/screens/home`.

![Saving the Python file live-reloads the screen on the phone](docs/hot-reload.gif)

*The dev loop: save the Python file, `uvicorn --reload` restarts the server, the shell
reconnects over WebSocket and renders the fresh screen — no rebuild, no reinstall. The
bottom bar is native (`BottomNavigationView` / `UITabBarController`), declared from
Python too.*

## Status

Young but real, built in public. Working today, on both shells, from one Python file:

- 19 components with a styling layer, native bottom bars, and routed screens —
  `@app.screen("product/{id}")` receives `ctx.params`, builders may be `async`
- Auth end to end: `@app.auth` returns your user object, guarded screens answer
  401/4401, the shells keep the bearer token encrypted (Keystore / Keychain) and
  fall back to your login screen
- A production mode: `Latawiec(dev=False, version=...)` switches phones from the
  live-reload socket to GET with a versioned disk cache — screens render instantly
  from the last-known copy, offline included, and a version bump drops every
  cached screen on the phones' next fetch
- Error and loading states, back stacks that keep screen state, and
  [a shipping guide](docs/shipping.md) that takes a branded shell to Play and
  App Store Connect
- Deep links: `latawiec://product/42` (or your own scheme) opens that screen,
  selecting its tab or pushing it onto the stack; https App Links / Universal
  Links take a manifest edit plus a well-known file on your domain

What it lacks is mileage: no third-party apps in production yet.

## Why so small

The release APK is **2.5 MB**, kept under a 3 MB CI budget — against 17.3 MB for
Flutter and 33.5 MB for React Native in
[SWMansion's same-app comparison](https://swmansion.com/blog/we-built-the-same-app-in-flutter-and-react-native-here-s-what-we-found/)
(2026). The
shell is plain native views plus DivKit and an HTTP client: no bundled runtime, no
webview. And because screens are server-side Python, **features weigh zero** — an
app with 500 screens ships the same shell as an app with five.

## Components

Layout: `Column`, `Row`, `Stack` (overlap), `Gallery` (scrolling list), `Grid`,
`Pager` with `Indicator` dots, in-screen `Tabs`, `Separator`, `Spacer`.
Content: `Text`, `Image`, `GifImage`, `Video`, `Button`.
Forms: `TextInput`, `Switch`, `Select`, `Slider` —
each binds a screen variable that any component can read reactively with a DivKit
expression (`Text("Hello, @{name}!")`), and `Submit` POSTs the values to the server.

Every component takes `style=Style(...)` — padding, margin, width/height (dp, `"fill"`,
`"wrap"`), background, corner radius, border, alignment, alpha — with `Edges` for
per-side spacing:

```python
lt.Text(
    "Box kite — $29",
    size=20,
    weight="medium",
    style=lt.Style(padding=12, background="#F5F5F5", corner_radius=16),
)
```

## How it works

```text
Python DSL (sdk-python/)  →  DivKit JSON over HTTP/WebSocket  →  native shell (Android/iOS)
```

- **sdk-python/** — the `latawiec` package: component DSL built on
  [pydivkit](https://pypi.org/project/pydivkit/) and the FastAPI-based screen server.
- **shell-android/** — a thin, fully native Kotlin app: DivKit renders whatever the server
  sends onto a view stack with real transitions. No Flutter, no React Native, no webview.
- **shell-ios/** — the same, in Swift (UIKit + DivKit); screens push onto a real
  UINavigationController, so back is the system back.
- **docs/shipping.md** — how a branded build of either shell gets to the stores.
- **mcp** (the `latawiec[mcp]` extra) — an MCP server so coding agents can build and
  preview Latawiec apps; see "For coding agents" below.

## For coding agents

The `latawiec[mcp]` extra ships an MCP server (`latawiec-mcp`, stdio) so agents can learn
the DSL (`reference`), list an app's screens, and render any screen to its DivKit JSON
without a server or a phone. Register it from `sdk-python/`:

```json
{ "mcpServers": { "latawiec": { "command": "uv", "args": ["run", "latawiec-mcp"] } } }
```

## Development

The Python side needs [uv](https://docs.astral.sh/uv/):

```sh
cd sdk-python
uv sync
uv run pytest
```

To see a screen on a phone, start the example server and install the shell on a running
emulator (the shell's default server URL is the emulator's host loopback):

```sh
cd sdk-python && uv run uvicorn examples.hello:app --host 0.0.0.0 --reload
cd shell-android && ./gradlew installDebug   # physical device: add -PserverUrl=http://<mac-ip>:8000
```

The iOS shell needs [XcodeGen](https://github.com/yonaskolb/XcodeGen) once
(`brew install xcodegen`); the simulator reaches the same server on the Mac's loopback:

```sh
cd shell-ios && xcodegen generate && open LatawiecShell.xcodeproj   # run on a simulator
```

Edit `examples/hello.py` while both are running and the phone follows your saves.
The other examples each show one pillar: `catalog.py` (a routed product list),
`tabs.py` (the native bottom bar), `auth.py` (sign-in and guarded screens), and
`prod.py` (production mode with the offline cache). The shells' UI tests run
against four of them — see CLAUDE.md for the ports.

## License

Apache-2.0
