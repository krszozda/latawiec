"""Example Latawiec app in production mode. Run from sdk-python/:

    uv run uvicorn examples.prod:app --host 0.0.0.0 --port 8004

dev=False switches the shells from the live-reload socket to GET with a
disk cache: screens render instantly from the last-known copy (offline
included) and revalidate in the background; the "about" screen is static
and lives until `version` changes. This app is also the fixture for the
shells' production-mode UI tests, which expect it on port 8004.
"""

import latawiec as lt

app = lt.Latawiec(dev=False, version="1")


@app.screen("home")
def home() -> lt.Component:
    return lt.Column(
        lt.Text("Prod home", size=28, weight="bold", style=lt.Style(margin=48)),
        lt.Button("About", on_tap=lt.Navigate("about"), style=lt.Style(margin=16)),
    )


@app.screen("about", cache="static")
def about() -> lt.Component:
    return lt.Column(lt.Text("About, cached as static", style=lt.Style(margin=48)))
