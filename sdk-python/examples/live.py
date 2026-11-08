"""Example Latawiec app with live and polled screens. Run from sdk-python/:

    uv run uvicorn examples.live:app --host 0.0.0.0 --port 8005

Production mode on purpose: the shells render over GET, then the live
screen subscribes and every `app.refresh` pushes a fresh render, while
the polled screen refetches on its interval. This app is also the
fixture for the shells' live-update UI tests, which expect it on port
8005; the texts below are what those tests assert.
"""

from datetime import datetime

import latawiec as lt

app = lt.Latawiec(dev=False, version="1", tabs=[lt.Tab("home", "Home")])

count = 0


# The chatbot use case, miniaturized: an action mutates the tabs and the
# shells pick the new bar up mid-session from the manifest fingerprint
# riding on every screen response. The UI tests drive these two directly.
@app.action("grow")
def grow(values: dict[str, str]) -> None:
    app.tabs = (lt.Tab("home", "Home"), lt.Tab("clock", "Clock"))


@app.action("reset")
def reset(values: dict[str, str]) -> None:
    app.tabs = (lt.Tab("home", "Home"),)


@app.screen("home", live=True)
def home() -> lt.Component:
    return lt.Column(
        lt.Text("Live counter", size=28, weight="bold", style=lt.Style(margin=48)),
        lt.Text(f"Count: {count}", size=20, style=lt.Style(margin=lt.Edges(left=16, right=16))),
        lt.Button("Bump", on_tap=lt.Submit("bump"), style=lt.Style(margin=16)),
        lt.Button("Open clock", on_tap=lt.Navigate("clock"), style=lt.Style(margin=16)),
    )


@app.action("bump")
def bump(values: dict[str, str]) -> None:
    global count
    count += 1
    app.refresh("home")


@app.screen("clock", refresh=1)
def clock() -> lt.Component:
    return lt.Column(
        lt.Text("Polled clock", size=28, weight="bold", style=lt.Style(margin=48)),
        lt.Text(
            f"Tick {datetime.now():%H:%M:%S}",
            size=20,
            style=lt.Style(margin=lt.Edges(left=16, right=16)),
        ),
    )
