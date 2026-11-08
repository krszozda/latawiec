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


# Keyed by platform: parallel Android and iOS test runs must not trample
# each other's state.
PULLS: dict[str, int] = {}


@app.screen("pull", refreshable=True)
def pull(ctx: lt.Context) -> lt.Component:
    PULLS[ctx.platform] = PULLS.get(ctx.platform, 0) + 1
    return lt.Gallery(
        lt.Text(f"Pulled {PULLS[ctx.platform]}", size=28, weight="bold", style=lt.Style(margin=48)),
        *[lt.Text(f"Row {i}", style=lt.Style(margin=lt.Edges(top=8, left=16))) for i in range(12)],
    )


ITEMS: dict[str, int] = {}


@app.screen("feed", live=True)
def feed(ctx: lt.Context) -> lt.Component:
    n = ITEMS.get(ctx.platform, 10)
    rows = [
        lt.Text(f"Item {i + 1}", style=lt.Style(margin=lt.Edges(top=10, left=16))) for i in range(n)
    ]
    more = [lt.LoadMore("page")] if n < 40 else []
    return lt.Gallery(
        lt.Text("Feed", size=28, weight="bold", style=lt.Style(margin=48)),
        *rows,
        *more,
    )


@app.action("page")
def page(values: dict[str, str], ctx: lt.Context) -> None:
    ITEMS[ctx.platform] = min(ITEMS.get(ctx.platform, 10) + 10, 40)
    app.refresh("feed")


@app.action("reset_feed")
def reset_feed(values: dict[str, str], ctx: lt.Context) -> None:
    ITEMS[ctx.platform] = 10
