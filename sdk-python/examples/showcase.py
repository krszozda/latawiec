"""The components, the taps, the live screens, the device and the store —
one app you can walk through.

Run it from sdk-python/:

    uv run uvicorn examples.showcase:app --host 0.0.0.0 --port 8010 --reload

then install the shell from the Releases page and give it this machine's
address. Set BASE below to the same address: an Android emulator reaches
this machine as 10.0.2.2, an iOS simulator as 127.0.0.1, and a real phone
only by this machine's address on the network. Nothing below is in the
app you installed — it is all this file.

Editing the file restarts the server, and the shell notices: a live
screen's connection drops and comes back with the new render, and any
other screen refetches when you return to it or pull it down.

Auth, push notifications and deep links have examples of their own in
this directory, because each needs a server set up for it. The rest of
those examples double as the shells' test fixtures; this one is for
reading.
"""

from pathlib import Path

import latawiec as lt

# Where this machine is, as the device sees it. An Android emulator:
# 10.0.2.2. An iOS simulator: 127.0.0.1. A real phone: this machine's
# address on your network, the same one you typed into the shell.
BASE = "http://10.0.2.2:8010"

app = lt.Latawiec(
    # Production mode, not the dev loop: pull-to-refresh and the screen
    # cache only exist here, because in dev mode every screen rides a
    # WebSocket instead and there is nothing to pull.
    dev=False,
    version="1",
    tabs=[
        lt.Tab("start", "Start", icon="/assets/home.png"),
        lt.Tab("pieces", "Pieces", icon="/assets/shop.png"),
        lt.Tab("moving", "Moving"),
        lt.Tab("device", "Device"),
    ],
    theme=lt.Theme(accent="#00695C"),
)
app.assets(str(Path(__file__).parent / "assets"))

GUTTER = lt.Style(margin=lt.Edges(left=16, right=16, top=8))
HEADING = lt.Style(margin=lt.Edges(left=16, right=16, top=32, bottom=8))


def note(text: str) -> lt.Component:
    """The line under each heading that says what to look at."""
    return lt.Text(text, size=14, color="#546E7A", style=GUTTER)


def asset(name: str) -> str:
    """An absolute URL for something this app serves.

    Image and Video hand their URL straight to the platform's loader, so a
    path like "/assets/kite.png" means nothing to it — unlike a tab icon,
    which the shell fetches itself and which may stay relative.
    """
    return f"{BASE}/assets/{name}"


# ---------------------------------------------------------------- start


@app.screen("start")
def start(ctx: lt.Context) -> lt.Component:
    return lt.Column(
        lt.Text("Latawiec", size=32, weight="bold", style=HEADING),
        note(
            "A Python file describes these screens; the app you are holding "
            "renders them with native views. Change the file and the change "
            "arrives — no store, no rebuild."
        ),
        lt.Text(
            f"Speaking to a {ctx.platform or 'mystery'} device"
            f"{f' in {ctx.locale}' if ctx.locale else ''}"
            f"{f', app version {ctx.app_version}' if ctx.app_version else ''}.",
            style=GUTTER,
        ),
        note("The server knows that much from the headers the shell sends."),
        lt.Button("What a screen is made of", on_tap=lt.Navigate("pieces"), style=GUTTER),
        lt.Button("What a tap can do", on_tap=lt.Navigate("taps"), style=GUTTER),
        lt.Button("What the device can tell you", on_tap=lt.Navigate("device"), style=GUTTER),
    )


# --------------------------------------------------------------- pieces


@app.screen("pieces")
def pieces() -> lt.Component:
    return lt.Gallery(
        lt.Text("Pieces", size=28, weight="bold", style=HEADING),
        note("Twenty-odd components, each one a native view underneath."),
        lt.Text("Text in sizes and weights", size=20, weight="bold", style=GUTTER),
        lt.Text("…and in a colour", color="#C2185B", style=GUTTER),
        lt.Row(
            lt.Image(asset("home.png"), style=lt.Style(width=48, height=48)),
            lt.Image(asset("shop.png"), style=lt.Style(width=48, height=48)),
            style=GUTTER,
        ),
        note("A Row of Images, sized and served by this app."),
        lt.Grid(
            *[
                lt.Text(
                    f"cell {i}",
                    style=lt.Style(background="#ECEFF1", padding=12, corner_radius=8),
                )
                for i in range(1, 7)
            ],
            columns=3,
            style=GUTTER,
        ),
        note("A Grid, three across."),
        lt.Pager(
            *[
                lt.Text(
                    f"page {i}",
                    size=24,
                    align="center",
                    style=lt.Style(background="#E0F2F1", padding=40, corner_radius=12),
                )
                for i in (1, 2, 3)
            ],
            id="pages",
            style=GUTTER,
        ),
        lt.Indicator(pager="pages", style=GUTTER),
        note("A swipeable Pager with its dots — swipe it."),
        lt.Separator(style=GUTTER),
        lt.Text("Form fields write into screen variables:", style=GUTTER),
        lt.TextInput("name", hint="Your name", style=GUTTER),
        lt.Text(lt.Expression("Hello, @{name}!"), size=20, style=GUTTER),
        note("That greeting updates as you type, on the device, with no round trip."),
        lt.Switch("fancy", style=GUTTER),
        lt.Text(lt.Expression("@{fancy ? 'Fancy mode on' : 'Fancy mode off'}"), style=GUTTER),
        lt.Select(
            "size",
            options=("Small", lt.Option("Medium", "m"), "Large"),
            hint="Pick a size",
            style=GUTTER,
        ),
        lt.Slider("many", min=0, max=10, initial=3, style=GUTTER),
        lt.Text(lt.Expression("Slider says @{many}"), style=GUTTER),
        lt.Spacer(height=32),
    )


# --------------------------------------------------------------- taps


@app.screen("taps")
def taps() -> lt.Component:
    return lt.Gallery(
        lt.Text("Taps", size=28, weight="bold", style=HEADING),
        note("Every button below is one line of Python."),
        lt.Button("Go to another screen", on_tap=lt.Navigate("pieces"), style=GUTTER),
        lt.Button("Set a variable", on_tap=lt.SetVariable("mood", "set!"), style=GUTTER),
        lt.Text(lt.Expression("Mood: @{mood}"), style=GUTTER),
        lt.Button("Tell the server", on_tap=lt.Submit("noted"), style=GUTTER),
        lt.Button("Copy a code", on_tap=lt.CopyToClipboard("kite-42"), style=GUTTER),
        lt.Button("Share some text", on_tap=lt.Share("Latawiec builds native apps"), style=GUTTER),
        lt.Button("Open a website", on_tap=lt.OpenUrl("https://example.com/"), style=GUTTER),
        lt.Button(
            "Buzz, then move",
            on_tap=(lt.Haptic("success"), lt.Navigate("pieces")),
            style=GUTTER,
        ),
        note("A tuple runs several actions in order."),
        lt.Button(
            "Confirm it's you, then tell the server",
            on_tap=lt.Unlock("noted", reason="Confirm this is you"),
            style=GUTTER,
        ),
        note(
            "Fingerprint, face or passcode in front of the tap. It gates the "
            "tap, not the server — a real handler still checks who is asking."
        ),
        lt.Spacer(height=32),
    )


@app.action("noted")
def noted(values: dict[str, str]) -> None:
    # A handler may answer with a Navigate; this one just takes the call.
    pass


# -------------------------------------------------------------- moving


# Demo state: in memory, shared by every phone of that platform, gone on
# restart. A real app keys this on the user, not on ctx.platform.
TICKS: dict[str, int] = {}


@app.screen("moving", live=True)
def moving(ctx: lt.Context) -> lt.Component:
    TICKS[ctx.platform] = TICKS.get(ctx.platform, 0) + 1
    return lt.Column(
        lt.Text("Moving", size=28, weight="bold", style=HEADING),
        note(
            "This screen is live: the server holds the connection and pushes a "
            "fresh render whenever it wants to."
        ),
        lt.Text(f"Rendered {TICKS[ctx.platform]} times", size=20, style=GUTTER),
        lt.Button("Push a new render", on_tap=lt.Submit("tick"), style=GUTTER),
        lt.Text(
            "Arrives with animation",
            align="center",
            style=lt.Style(
                background="#E0F2F1",
                padding=16,
                corner_radius=12,
                margin=lt.Edges(left=16, right=16, top=16),
                appear=lt.Slide(edge="right"),
            ),
        ),
        note("Style(appear=…) animates anything that arrives, streamed or not."),
        lt.Button("A feed that loads as you scroll", on_tap=lt.Navigate("feed"), style=GUTTER),
        lt.Button("A screen you pull to refresh", on_tap=lt.Navigate("pulled"), style=GUTTER),
        lt.Spacer(height=24),
    )


@app.action("tick")
def tick(values: dict[str, str]) -> None:
    app.refresh("moving")


ROWS: dict[str, int] = {}


@app.screen("feed", live=True)
def feed(ctx: lt.Context) -> lt.Component:
    rows = ROWS.get(ctx.platform, 20)
    return lt.Gallery(
        lt.Text("A feed", size=28, weight="bold", style=HEADING),
        note("Scroll to the end and the next page arrives on its own."),
        *[
            lt.Text(f"Item {i}", style=lt.Style(margin=lt.Edges(top=12, left=16)))
            for i in range(1, rows + 1)
        ],
        # Rendered only while there is more: a sentinel left in an exhausted
        # list would ask again on every refresh.
        *([lt.LoadMore("more")] if rows < 60 else []),
    )


@app.action("more")
def more(values: dict[str, str], ctx: lt.Context) -> None:
    ROWS[ctx.platform] = min(ROWS.get(ctx.platform, 20) + 20, 60)
    app.refresh("feed")


PULLS: dict[str, int] = {}


@app.screen("pulled", refreshable=True)
def pulled(ctx: lt.Context) -> lt.Component:
    PULLS[ctx.platform] = PULLS.get(ctx.platform, 0) + 1
    return lt.Gallery(
        lt.Text("Pull me down", size=28, weight="bold", style=HEADING),
        note("refreshable=True gives the screen the platform's own gesture."),
        lt.Text(f"Fetched {PULLS[ctx.platform]} times", size=20, style=GUTTER),
        *[
            lt.Text(f"Row {i}", style=lt.Style(margin=lt.Edges(top=12, left=16)))
            for i in range(1, 15)
        ],
    )


# -------------------------------------------------------------- device


@app.screen("device")
def device() -> lt.Component:
    return lt.Gallery(
        lt.Text("Device", size=28, weight="bold", style=HEADING),
        note(
            "Each of these asks the platform for something, with the system's "
            "own prompt. None of them costs the app a dependency."
        ),
        lt.Text("Where am I", size=20, weight="bold", style=GUTTER),
        lt.Button("Find me", on_tap=lt.RequestLocation("spot", then="noted"), style=GUTTER),
        lt.Text(lt.Expression("At @{spot}"), style=GUTTER),
        lt.Separator(style=GUTTER),
        lt.Text("A photo", size=20, weight="bold", style=GUTTER),
        lt.ImagePicker("gallery_shot", style=GUTTER),
        lt.ImagePicker("camera_shot", source="camera", style=GUTTER),
        note("The gallery and the camera, both uploading to @app.upload."),
        lt.Separator(style=GUTTER),
        lt.Text("A map", size=20, weight="bold", style=GUTTER),
        lt.Map(
            52.2297,
            21.0122,
            zoom=11,
            height=260,
            markers=(
                # Labels the tiles do not already carry, so both are legible.
                lt.Marker(52.2297, 21.0122, "Office"),
                lt.Marker(50.0647, 19.9450, "Branch"),
            ),
            style=GUTTER,
        ),
        note("Pan and zoom it: MapKit on iOS, a tile view on Android."),
        lt.Separator(style=GUTTER),
        lt.Text("A video", size=20, weight="bold", style=GUTTER),
        lt.Video(asset("clip.mp4"), autoplay=True, loop=True, muted=True, style=GUTTER),
        note("The platform player. DASH needs an Android build with -PwithVideo."),
        lt.Button("Something to buy", on_tap=lt.Navigate("shop"), style=GUTTER),
        lt.Spacer(height=32),
    )


@app.upload
def receive(file: lt.Upload) -> str:
    # A real app stores the bytes and returns their URL; this one echoes a
    # known image back so the picker has something to preview.
    return f"{asset('home.png')}?bytes={len(file.data)}"


RECEIPTS: dict[str, str] = {}


@app.screen("shop", live=True)
def shop(ctx: lt.Context) -> lt.Component:
    return lt.Column(
        lt.Text("Shop", size=28, weight="bold", style=HEADING),
        note(
            "The store's own flow, then a receipt for your server to verify. "
            "Needs a product with this id in App Store Connect or Play "
            "Console — and on Android a build with -PwithBilling."
        ),
        lt.Button(
            "Buy a kite — 0.99",
            on_tap=lt.Purchase("kite.one", "granted", consumable=True),
            style=GUTTER,
        ),
        lt.Text(RECEIPTS.get(ctx.platform, "Nothing bought yet"), style=GUTTER),
    )


@app.action("granted")
def granted(values: dict[str, str], ctx: lt.Context) -> None:
    # What a real handler does here: verify the receipt with Apple or
    # Google, read the product out of the *verified* receipt rather than
    # the request, refuse a transaction it has already granted, and only
    # then give the customer their kite.
    receipt = values.get("receipt", "")
    RECEIPTS[ctx.platform] = f"A receipt of {len(receipt)} characters arrived — verify it!"
    app.refresh("shop")
