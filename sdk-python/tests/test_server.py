import threading
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
    def check(token: str | None) -> str | None:
        return "friend" if token == "s3cret" else None

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


def test_screen_template_captures_path_params() -> None:
    routed = lt.Latawiec()

    @routed.screen("product/{id}")
    def product(ctx: lt.Context) -> lt.Component:
        return lt.Column(lt.Text(f"Product {ctx.params['id']}"))

    response = TestClient(routed).get("/screens/product/42")

    assert response.status_code == 200
    div = response.json()["card"]["states"][0]["div"]
    assert div["items"][0]["text"] == "Product 42"


def test_exact_screen_name_beats_a_template() -> None:
    routed = lt.Latawiec()

    @routed.screen("product/{id}")
    def product(ctx: lt.Context) -> lt.Component:
        return lt.Column(lt.Text("from template"))

    @routed.screen("product/new")
    def new() -> lt.Component:
        return lt.Column(lt.Text("exact"))

    div = TestClient(routed).get("/screens/product/new").json()["card"]["states"][0]["div"]
    assert div["items"][0]["text"] == "exact"


def test_unknown_path_is_404_and_render_screen_resolves_templates() -> None:
    routed = lt.Latawiec()

    @routed.screen("product/{id}")
    def product(ctx: lt.Context) -> lt.Component:
        return lt.Column(lt.Text(ctx.params["id"]))

    assert TestClient(routed).get("/screens/product/42/extra").status_code == 404
    card = routed.render_screen("product/7")
    assert card["card"]["states"][0]["div"]["items"][0]["text"] == "7"
    assert routed.screen_names == ("product/{id}",)


def test_screen_socket_serves_slashed_names() -> None:
    routed = lt.Latawiec()

    @routed.screen("product/{id}")
    def product(ctx: lt.Context) -> lt.Component:
        return lt.Column(lt.Text(f"ws {ctx.params['id']}"))

    with TestClient(routed).websocket_connect("/ws/screens/product/9") as socket:
        payload = socket.receive_json()
    assert payload["card"]["states"][0]["div"]["items"][0]["text"] == "ws 9"


def test_builders_and_handlers_receive_the_user() -> None:
    guarded = guarded_app()

    @guarded.screen("whoami")
    def whoami(ctx: lt.Context) -> lt.Component:
        return lt.Column(lt.Text(f"You are {ctx.user}"))

    seen: list[str | None] = []

    @guarded.action("record")
    def record(values: dict[str, str], ctx: lt.Context) -> None:
        seen.append(ctx.user)

    client = TestClient(guarded)
    div = client.get("/screens/whoami", headers=BEARER).json()["card"]["states"][0]["div"]
    assert div["items"][0]["text"] == "You are friend"
    client.post("/actions/record", json={}, headers=BEARER)
    assert seen == ["friend"]


def test_async_builders_handlers_and_auth_work() -> None:
    app = lt.Latawiec()

    @app.auth
    async def check(token: str | None) -> str | None:
        return "async-user" if token == "t" else None

    @app.screen("home")
    async def home(ctx: lt.Context) -> lt.Component:
        return lt.Column(lt.Text(f"async {ctx.user}"))

    @app.action("do", public=True)
    async def do(values: dict[str, str]) -> lt.Navigate:
        return lt.Navigate("home")

    client = TestClient(app)
    div = client.get("/screens/home", headers={"Authorization": "Bearer t"}).json()["card"][
        "states"
    ][0]["div"]
    assert div["items"][0]["text"] == "async async-user"
    assert client.post("/actions/do", json={}).json() == {"navigate": "home"}


def test_sync_builders_run_off_the_event_loop() -> None:
    app = lt.Latawiec()
    threads: list[int] = []

    @app.screen("home")
    def home() -> lt.Component:
        threads.append(threading.get_ident())
        return lt.Column(lt.Text("x"))

    client = TestClient(app)

    @app.get("/loop-thread")
    async def loop_thread() -> dict[str, int]:
        return {"ident": threading.get_ident()}

    loop_ident = client.get("/loop-thread").json()["ident"]
    assert client.get("/screens/home").status_code == 200
    assert threads and threads[0] != loop_ident


def test_render_screen_drives_async_builders() -> None:
    app = lt.Latawiec()

    @app.screen("home")
    async def home() -> lt.Component:
        return lt.Column(lt.Text("rendered"))

    card = app.render_screen("home")
    assert card["card"]["states"][0]["div"]["items"][0]["text"] == "rendered"


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
