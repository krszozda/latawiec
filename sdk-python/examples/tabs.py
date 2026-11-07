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
