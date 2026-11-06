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

## Status

Early development, built in public. Working today: a small Python DSL (text, image,
column/row, buttons with navigate actions), a FastAPI server that exposes screens as
DivKit card JSON, and an Android shell that renders a screen from that server. Not working
yet: tap actions in the shell, the iOS shell, state, hot reload.

## How it will work

```text
Python DSL (sdk-python/)  →  DivKit JSON over HTTP/WebSocket  →  native shell (Android/iOS)
```

- **sdk-python/** — the `latawiec` package: component DSL built on
  [pydivkit](https://pypi.org/project/pydivkit/) and the FastAPI-based screen server;
  a dev server with hot reload comes next.
- **shell-android/** — a thin, fully native Kotlin app: DivKit renders whatever the server
  sends. No Flutter, no React Native, no webview.
- **shell-ios/** (planned) — the same, in Swift.
- **mcp/** (planned) — an MCP server so coding agents can build and preview Latawiec apps.

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
cd sdk-python && uv run uvicorn examples.hello:app --host 0.0.0.0
cd shell-android && ./gradlew installDebug   # physical device: add -PserverUrl=http://<mac-ip>:8000
```

## License

Apache-2.0
