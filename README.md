# Latawiec

**Latawiec** (Polish for *kite*) — native mobile apps flown from a Python backend.

A kite flies in the sky, but the string stays in your hand. Latawiec works the same way:
screens are written in Python on your server, and a thin native shell on the phone renders
them natively with [DivKit](https://divkit.tech). Change the Python, and the app changes —
no app release, no Kotlin, no Swift.

```python
import latawiec as lt

screen = lt.Column(
    lt.Text("Hello from the server", size=24),
)
```

## Status

Early development, built in public. Working today: a minimal Python DSL that renders to
DivKit card JSON. Not working yet: everything else — the native shells, actions, navigation,
state, hot reload.

## How it will work

```
Python DSL (sdk-python/)  →  DivKit JSON over HTTP/WebSocket  →  native shell (Android/iOS)
```

- **sdk-python/** — the `latawiec` package: component DSL built on
  [pydivkit](https://pypi.org/project/pydivkit/), later a FastAPI server and a dev server
  with hot reload.
- **shell-android/**, **shell-ios/** (planned) — thin native apps that connect to a Latawiec
  server and render whatever it sends.
- **mcp/** (planned) — an MCP server so coding agents can build and preview Latawiec apps.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
cd sdk-python
uv sync
uv run pytest
```

## License

Apache-2.0
