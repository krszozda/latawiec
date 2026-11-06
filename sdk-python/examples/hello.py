"""Example Latawiec app. Run from sdk-python/:

    uv run uvicorn examples.hello:app --host 0.0.0.0

then launch the Android shell; it fetches /screens/home.
"""

import latawiec as lt

app = lt.Latawiec()


@app.screen("home")
def home() -> lt.Component:
    return lt.Column(
        lt.Text("Hello from Python", size=28),
        lt.Text("This screen was rendered natively by DivKit."),
        lt.Button("Checkout", on_tap=lt.Navigate("checkout")),
    )


@app.screen("checkout")
def checkout() -> lt.Component:
    return lt.Column(
        lt.Text("Checkout", size=28),
        lt.Text("A server-defined button brought you here; system back returns home."),
    )
