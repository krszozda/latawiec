"""Example Latawiec app behind a sign-in. Run from sdk-python/:

    uv run uvicorn examples.auth:app --host 0.0.0.0 --port 8002

The home screen is guarded: a fresh shell gets 4401, falls back to the
manifest's login screen, and signs in with the code "sezam". This app is
also the fixture for the shells' auth UI tests, which expect it on port
8002; the texts below are what those tests assert.
"""

import secrets

import latawiec as lt

app = lt.Latawiec(login="signin")

# One token per server run; a real app would issue one per user session.
TOKEN = secrets.token_urlsafe(16)


@app.auth
def check(token: str | None) -> bool:
    return token == TOKEN


@app.screen("signin", public=True)
def signin() -> lt.Component:
    return lt.Column(
        lt.Text("Sign in", size=28, weight="bold", style=lt.Style(margin=48)),
        lt.TextInput("code", hint="Access code", style=lt.Style(margin=16)),
        lt.Button(
            "Enter",
            on_tap=lt.Submit("sign-in", send=("code",)),
            style=lt.Style(margin=16),
        ),
    )


@app.action("sign-in", public=True)
def sign_in(values: dict[str, str]) -> lt.Grant | None:
    if values.get("code") != "sezam":
        return None
    return lt.Grant(token=TOKEN, screen="home")


@app.screen("home")
def home() -> lt.Component:
    return lt.Column(
        lt.Text("Signed in", size=28, weight="bold", style=lt.Style(margin=48)),
        lt.Text("Only a valid token renders this screen.", style=lt.Style(margin=16)),
    )
