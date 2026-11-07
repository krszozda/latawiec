from pathlib import Path

from fastapi.testclient import TestClient

import latawiec as lt

app = lt.Latawiec()


@app.screen("home")
def home() -> lt.Component:
    return lt.Column(lt.Text("Hello"))


submitted: list[dict[str, str]] = []


@app.action("register")
def register(values: dict[str, str]) -> lt.Navigate:
    submitted.append(values)
    return lt.Navigate("home")


@app.action("log")
def log(values: dict[str, str]) -> None:
    submitted.append(values)


client = TestClient(app)


def test_screen_endpoint_returns_rendered_card() -> None:
    response = client.get("/screens/home")

    assert response.status_code == 200
    div = response.json()["card"]["states"][0]["div"]
    assert div["items"][0]["text"] == "Hello"


def test_unknown_screen_is_404() -> None:
    assert client.get("/screens/nope").status_code == 404


def test_action_gets_values_and_answers_with_navigation() -> None:
    response = client.post("/actions/register", json={"name": "kite"})

    assert response.status_code == 200
    assert response.json() == {"navigate": "home"}
    assert submitted[-1] == {"name": "kite"}


def test_action_without_navigation_answers_null() -> None:
    response = client.post("/actions/log", json={})

    assert response.json() == {"navigate": None}


def test_unknown_action_is_404() -> None:
    assert client.post("/actions/nope", json={}).status_code == 404


def test_screen_socket_sends_rendered_card_on_connect() -> None:
    with client.websocket_connect("/ws/screens/home") as socket:
        payload = socket.receive_json()

    div = payload["card"]["states"][0]["div"]
    assert div["items"][0]["text"] == "Hello"


def test_screen_socket_closes_unknown_screen_with_4404() -> None:
    with client.websocket_connect("/ws/screens/nope") as socket:
        message = socket.receive()

    assert message["type"] == "websocket.close"
    assert message["code"] == 4404


def test_manifest_defaults_to_no_tabs_and_default_theme() -> None:
    response = client.get("/manifest")

    assert response.status_code == 200
    assert response.json() == {"tabs": [], "theme": {"accent": "#2962FF"}, "login": None}


def test_manifest_lists_tabs_and_theme() -> None:
    tabbed = lt.Latawiec(
        tabs=[
            lt.Tab("home", "Home", icon="/assets/home.png"),
            lt.Tab("cart", "Cart"),
        ],
        theme=lt.Theme(accent="#00695C"),
    )

    response = TestClient(tabbed).get("/manifest")

    assert response.json() == {
        "tabs": [
            {"screen": "home", "title": "Home", "icon": "/assets/home.png"},
            {"screen": "cart", "title": "Cart", "icon": None},
        ],
        "theme": {"accent": "#00695C"},
        "login": None,
    }


def test_assets_serves_files_from_the_mounted_directory(tmp_path: Path) -> None:
    (tmp_path / "home.png").write_bytes(b"not really a png")
    serving = lt.Latawiec()
    serving.assets(str(tmp_path))

    response = TestClient(serving).get("/assets/home.png")

    assert response.status_code == 200
    assert response.content == b"not really a png"


def guarded_app() -> lt.Latawiec:
    guarded = lt.Latawiec(login="signin")

    @guarded.auth
    def check(token: str | None) -> bool:
        return token == "s3cret"

    @guarded.screen("signin", public=True)
    def signin() -> lt.Component:
        return lt.Column(lt.TextInput("code"))

    @guarded.screen("home")
    def home() -> lt.Component:
        return lt.Column(lt.Text("Hello"))

    @guarded.action("sign-in", public=True)
    def sign_in(values: dict[str, str]) -> lt.Grant:
        return lt.Grant(token="s3cret", screen="home")

    @guarded.action("buy")
    def buy(values: dict[str, str]) -> None:
        return None

    return guarded


BEARER = {"Authorization": "Bearer s3cret"}


def test_guarded_screen_needs_the_right_token() -> None:
    guarded = TestClient(guarded_app())

    assert guarded.get("/screens/home").status_code == 401
    wrong = {"Authorization": "Bearer nope"}
    assert guarded.get("/screens/home", headers=wrong).status_code == 401
    basic = {"Authorization": "Basic s3cret"}
    assert guarded.get("/screens/home", headers=basic).status_code == 401
    assert guarded.get("/screens/home", headers=BEARER).status_code == 200


def test_public_screen_and_manifest_stay_open() -> None:
    guarded = TestClient(guarded_app())

    assert guarded.get("/screens/signin").status_code == 200
    manifest = guarded.get("/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["login"] == "signin"


def test_guarded_action_needs_the_token() -> None:
    guarded = TestClient(guarded_app())

    assert guarded.post("/actions/buy", json={}).status_code == 401
    assert guarded.post("/actions/buy", json={}, headers=BEARER).status_code == 200


def test_sign_in_action_answers_with_a_grant() -> None:
    guarded = TestClient(guarded_app())

    response = guarded.post("/actions/sign-in", json={"code": "kite"})

    assert response.status_code == 200
    assert response.json() == {"navigate": "home", "token": "s3cret"}


def test_guarded_socket_closes_with_4401() -> None:
    guarded = TestClient(guarded_app())

    with guarded.websocket_connect("/ws/screens/home") as socket:
        message = socket.receive()
    assert message["type"] == "websocket.close"
    assert message["code"] == 4401

    with guarded.websocket_connect("/ws/screens/home", headers=BEARER) as socket:
        payload = socket.receive_json()
    assert payload["card"]["states"][0]["div"]["items"][0]["text"] == "Hello"


def test_public_socket_needs_no_token() -> None:
    guarded = TestClient(guarded_app())

    with guarded.websocket_connect("/ws/screens/signin") as socket:
        payload = socket.receive_json()
    assert payload["card"]["states"][0]["div"]["items"][0]["type"] == "input"
