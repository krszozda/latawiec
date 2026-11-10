"""Example Latawiec app with a native bottom bar. Run from sdk-python/:

    uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001

The shells read `GET /manifest` at startup and build the bar natively —
BottomNavigationView on Android, UITabBarController on iOS. This app is
also the fixture for the shells' tab-bar UI tests, which expect it on
port 8001; the texts below are what those tests assert.
"""

from pathlib import Path

import latawiec as lt

app = lt.Latawiec(
    tabs=[
        lt.Tab("home", "Home", icon="/assets/home.png"),
        lt.Tab("shop", "Shop", icon="/assets/shop.png"),
        lt.Tab("form", "Form"),
    ],
    theme=lt.Theme(accent="#00695C"),
)
app.assets(str(Path(__file__).parent / "assets"))


@app.screen("home")
def home() -> lt.Component:
    return lt.Column(
        lt.Text("Home tab", size=28, weight="bold", style=lt.Style(margin=48)),
        lt.Button("Open details", on_tap=lt.Navigate("details"), style=lt.Style(margin=16)),
    )


@app.screen("details")
def details() -> lt.Component:
    return lt.Column(lt.Text("Details inside the Home tab", style=lt.Style(margin=48)))


@app.screen("shop")
def shop() -> lt.Component:
    return lt.Column(lt.Text("Shop tab", size=28, weight="bold", style=lt.Style(margin=48)))


@app.screen("form")
def form() -> lt.Component:
    return lt.Column(
        lt.Text("Form tab", size=28, weight="bold", style=lt.Style(margin=48)),
        lt.TextInput("name", hint="Your name", style=lt.Style(margin=16)),
    )


@app.upload
def receive_photo(file: lt.Upload, ctx: lt.Context) -> str:
    # The fixture only proves the round trip: echo a known image back, with
    # the byte count in the query so tests can assert it arrived whole.
    host = "10.0.2.2" if ctx.platform == "android" else "127.0.0.1"
    return f"http://{host}:8001/assets/home.png?bytes={len(file.data)}"


@app.screen("photo")
def photo() -> lt.Component:
    return lt.Column(
        lt.Text("Pick a photo", size=28, weight="bold", style=lt.Style(margin=48)),
        lt.ImagePicker("snap", style=lt.Style(margin=16)),
        lt.Text("@{snap}", size=12, color="#757575", style=lt.Style(margin=16)),
        lt.Button("Send it", on_tap=lt.Submit("keep", send=("snap",)), style=lt.Style(margin=16)),
    )


@app.action("keep")
def keep(values: dict[str, str]) -> None:
    pass


@app.screen("system")
def system(ctx: lt.Context) -> lt.Component:
    gutter = lt.Style(margin=lt.Edges(top=12, left=16, right=16))
    return lt.Column(
        lt.Text("System actions", size=28, weight="bold", style=lt.Style(margin=48)),
        lt.Text(
            f"Seen from {ctx.platform or 'somewhere'}, speaking {ctx.locale or 'anything'}",
            color="#757575",
            style=lt.Style(margin=lt.Edges(left=16, right=16)),
        ),
        lt.Button("Copy code", on_tap=lt.CopyToClipboard("kite-42"), style=gutter),
        lt.Button("Share it", on_tap=lt.Share("Kites are great"), style=gutter),
        lt.Button("Open the site", on_tap=lt.OpenUrl("https://example.com/"), style=gutter),
        lt.Button("Buzz", on_tap=(lt.Haptic("success"), lt.Navigate("details")), style=gutter),
    )


# Keyed by platform: parallel Android and iOS test runs must not trample
# each other's state.
SPOTS: dict[str, str] = {}


VAULTS: dict[str, bool] = {}


@app.screen("vault", live=True)
def vault(ctx: lt.Context) -> lt.Component:
    return lt.Column(
        lt.Text("Vault", size=28, weight="bold", style=lt.Style(margin=48)),
        lt.Button(
            "Unlock it",
            on_tap=lt.Unlock("open_vault", reason="Confirm it's you"),
            style=lt.Style(margin=16),
        ),
        lt.Text(
            "Open" if VAULTS.get(ctx.platform) else "Locked",
            style=lt.Style(margin=lt.Edges(left=16, right=16)),
        ),
    )


@app.action("open_vault")
def open_vault(values: dict[str, str], ctx: lt.Context) -> None:
    VAULTS[ctx.platform] = True
    app.refresh("vault")


@app.action("lock_vault")
def lock_vault(values: dict[str, str], ctx: lt.Context) -> None:
    # The UI tests call this first: a vault left open by the last run would
    # let the assertion pass without the shell doing anything.
    VAULTS.pop(ctx.platform, None)
    app.refresh("vault")


BOUGHT: dict[str, str] = {}


@app.screen("shop_kite", live=True)
def shop_kite(ctx: lt.Context) -> lt.Component:
    return lt.Column(
        lt.Text("Kite shop", size=28, weight="bold", style=lt.Style(margin=48)),
        lt.Button(
            "Buy a kite",
            on_tap=lt.Purchase("kite.one", "grant_kite", consumable=True),
            style=lt.Style(margin=16),
        ),
        lt.Button(
            "Forget it",
            on_tap=lt.Submit("forget_kite"),
            color="#607D8B",
            style=lt.Style(margin=lt.Edges(left=16, right=16)),
        ),
        lt.Text(
            BOUGHT.get(ctx.platform, "Nothing bought"),
            style=lt.Style(margin=lt.Edges(left=16, right=16)),
        ),
    )


@app.action("grant_kite")
def grant_kite(values: dict[str, str], ctx: lt.Context) -> None:
    # A real handler verifies this with Apple or Google, reads the product
    # out of the verified receipt, and refuses a transaction id it has
    # already granted. The fixture deliberately grants nothing — it only
    # reports that a receipt arrived, so the tests can see it did.
    receipt = values.get("receipt", "")
    BOUGHT[ctx.platform] = f"Receipt of {len(receipt)} chars arrived"
    app.refresh("shop_kite")


@app.action("forget_kite")
def forget_kite(values: dict[str, str], ctx: lt.Context) -> None:
    # The UI tests tap this to start from nothing.
    BOUGHT.pop(ctx.platform, None)
    app.refresh("shop_kite")


@app.screen("clip")
def clip(ctx: lt.Context) -> lt.Component:
    # The emulator reaches the host by a different name than the simulator.
    host = "10.0.2.2" if ctx.platform == "android" else "127.0.0.1"
    return lt.Column(
        lt.Text("A short clip", size=28, weight="bold", style=lt.Style(margin=48)),
        lt.Video(
            f"http://{host}:8001/assets/clip.mp4",
            autoplay=True,
            loop=True,
            muted=True,
            style=lt.Style(margin=16),
        ),
    )


@app.screen("map")
def map_screen() -> lt.Component:
    return lt.Column(
        lt.Text("Where we fly", size=28, weight="bold", style=lt.Style(margin=48)),
        lt.Map(
            52.2297,
            21.0122,
            zoom=12,
            height=320,
            markers=(
                lt.Marker(52.2297, 21.0122, "Warszawa"),
                lt.Marker(50.0647, 19.9450, "Kraków"),
            ),
            style=lt.Style(margin=16),
        ),
    )


@app.screen("shoot")
def shoot() -> lt.Component:
    return lt.Column(
        lt.Text("Snapshot", size=28, weight="bold", style=lt.Style(margin=48)),
        # No label: the component says "Take a photo" because of the source.
        lt.ImagePicker("shot", source="camera", style=lt.Style(margin=16)),
        lt.Text("@{shot}", size=12, color="#757575", style=lt.Style(margin=16)),
    )


@app.screen("where", live=True)
def where(ctx: lt.Context) -> lt.Component:
    return lt.Column(
        lt.Text("Where am I", size=28, weight="bold", style=lt.Style(margin=48)),
        lt.Button(
            "Find me",
            on_tap=lt.RequestLocation("spot", then="note_spot"),
            style=lt.Style(margin=16),
        ),
        lt.Text("At @{spot}", style=lt.Style(margin=lt.Edges(left=16, right=16))),
        lt.Text(
            f"Server saw {SPOTS.get(ctx.platform, 'nothing')}",
            color="#757575",
            style=lt.Style(margin=lt.Edges(top=12, left=16, right=16)),
        ),
    )


@app.action("note_spot")
def note_spot(values: dict[str, str], ctx: lt.Context) -> None:
    SPOTS[ctx.platform] = values.get("spot") or "nothing"
    app.refresh("where")


@app.action("forget_spot")
def forget_spot(values: dict[str, str], ctx: lt.Context) -> None:
    # The UI tests call this first: a fix left over from the last run would
    # let the assertion pass without the shell doing anything.
    SPOTS.pop(ctx.platform, None)
    app.refresh("where")
