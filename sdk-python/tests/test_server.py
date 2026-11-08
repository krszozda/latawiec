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
    assert response.json() == {
        "tabs": [],
        "theme": {"accent": "#2962FF"},
        "login": None,
        "version": None,
        "dev": True,
        "push": False,
    }


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
        "version": None,
        "dev": True,
        "push": False,
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


def test_cache_policy_rides_in_cache_control_headers() -> None:
    app = lt.Latawiec(version="2026.11.07", dev=False)

    @app.screen("about", cache="static")
    def about() -> lt.Component:
        return lt.Column(lt.Text("about"))

    @app.screen("home")
    def home() -> lt.Component:
        return lt.Column(lt.Text("home"))

    @app.screen("wallet", cache="no-store")
    def wallet() -> lt.Component:
        return lt.Column(lt.Text("wallet"))

    client = TestClient(app)
    assert client.get("/screens/about").headers["Cache-Control"] == "max-age=31536000, immutable"
    assert (
        client.get("/screens/home").headers["Cache-Control"]
        == "max-age=0, stale-while-revalidate=86400"
    )
    assert client.get("/screens/wallet").headers["Cache-Control"] == "no-store"
    manifest = client.get("/manifest").json()
    assert manifest["version"] == "2026.11.07"
    assert manifest["dev"] is False


def test_guarded_screens_default_to_no_store() -> None:
    guarded = guarded_app()

    @guarded.screen("terms", cache="static")
    def terms() -> lt.Component:
        return lt.Column(lt.Text("terms"))

    client = TestClient(guarded)

    assert client.get("/screens/home", headers=BEARER).headers["Cache-Control"] == "no-store"
    # An explicit policy overrides the guarded default.
    static = client.get("/screens/terms", headers=BEARER).headers["Cache-Control"]
    assert static == "max-age=31536000, immutable"
    assert (
        client.get("/screens/signin").headers["Cache-Control"]
        == "max-age=0, stale-while-revalidate=86400"
    )


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


DEVICE_HEADERS = {
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
    "X-Latawiec-Platform": "Android",
    "X-Latawiec-Timezone": "Europe/Warsaw",
    "X-Latawiec-App-Version": "1.2",
}


def _device_app() -> lt.Latawiec:
    probed = lt.Latawiec()

    @probed.screen("probe")
    def probe(ctx: lt.Context) -> lt.Component:
        return lt.Text(f"{ctx.locale}|{ctx.platform}|{ctx.timezone}|{ctx.app_version}")

    return probed


def test_screen_context_carries_the_device_headers() -> None:
    response = TestClient(_device_app()).get("/screens/probe", headers=DEVICE_HEADERS)

    div = response.json()["card"]["states"][0]["div"]
    assert div["text"] == "pl-PL|android|Europe/Warsaw|1.2"
    # Shared HTTP caches must key cacheable renders on the device headers.
    assert "Accept-Language" in response.headers["vary"]
    assert "X-Latawiec-Platform" in response.headers["vary"]


def test_device_context_is_empty_for_a_plain_client() -> None:
    response = TestClient(_device_app()).get("/screens/probe")

    div = response.json()["card"]["states"][0]["div"]
    assert div["text"] == "|||"


def test_a_wildcard_accept_language_is_not_a_locale() -> None:
    response = TestClient(_device_app()).get("/screens/probe", headers={"Accept-Language": "*"})

    div = response.json()["card"]["states"][0]["div"]
    assert div["text"] == "|||"


def test_socket_context_carries_the_device_headers() -> None:
    with TestClient(_device_app()).websocket_connect(
        "/ws/screens/probe", headers=DEVICE_HEADERS
    ) as socket:
        payload = socket.receive_json()

    assert payload["card"]["states"][0]["div"]["text"] == "pl-PL|android|Europe/Warsaw|1.2"


def test_action_context_carries_the_device_headers() -> None:
    probed = _device_app()

    @probed.action("whereami")
    def whereami(values: dict[str, str], ctx: lt.Context) -> lt.Navigate:
        return lt.Navigate(f"welcome/{ctx.locale}/{ctx.platform}")

    response = TestClient(probed).post("/actions/whereami", json={}, headers=DEVICE_HEADERS)
    assert response.json() == {"navigate": "welcome/pl-PL/android"}


def test_device_registration_feeds_the_hook_and_flips_the_manifest_flag() -> None:
    pushed = lt.Latawiec()
    tokens: list[tuple[str, str]] = []

    @pushed.device
    def device(token: str, ctx: lt.Context) -> None:
        tokens.append((token, ctx.platform))

    probe = TestClient(pushed)
    assert probe.get("/manifest").json()["push"] is True

    response = probe.post(
        "/devices", json={"token": "fcm-abc"}, headers={"X-Latawiec-Platform": "android"}
    )
    assert response.json() == {"registered": True}
    assert tokens == [("fcm-abc", "android")]


def test_device_registration_without_a_hook_is_404() -> None:
    assert client.post("/devices", json={"token": "t"}).status_code == 404


def test_device_registration_requires_a_token() -> None:
    pushed = lt.Latawiec()

    @pushed.device
    def device(token: str) -> None:  # pragma: no cover - never reached
        raise AssertionError

    assert TestClient(pushed).post("/devices", json={}).status_code == 422


def test_device_handler_may_skip_the_context() -> None:
    pushed = lt.Latawiec()
    tokens: list[str] = []

    @pushed.device
    def device(token: str) -> None:
        tokens.append(token)

    assert TestClient(pushed).post("/devices", json={"token": "bare"}).status_code == 200
    assert tokens == ["bare"]


def test_device_registration_stays_public_but_learns_the_user() -> None:
    pushed = lt.Latawiec()
    seen: list[str | None] = []

    @pushed.auth
    def auth(token: str | None) -> str | None:
        return "pat" if token == "sezam" else None

    @pushed.device
    def device(token: str, ctx: lt.Context) -> None:
        seen.append(ctx.user)

    probe = TestClient(pushed)
    assert probe.post("/devices", json={"token": "t"}).status_code == 200
    probe.post("/devices", json={"token": "t"}, headers={"Authorization": "Bearer sezam"})
    assert seen == [None, "pat"]


def _counter_app() -> tuple[lt.Latawiec, dict[str, int]]:
    counter = {"n": 0}
    live_app = lt.Latawiec()

    @live_app.screen("counter", live=True)
    def counter_screen() -> lt.Component:
        return lt.Text(f"Count: {counter['n']}")

    @live_app.screen("clock", refresh=5)
    def clock() -> lt.Component:
        return lt.Text("tick")

    return live_app, counter


def test_live_and_polled_screens_declare_themselves_in_headers() -> None:
    live_app, _ = _counter_app()
    with TestClient(live_app) as probe:
        assert probe.get("/screens/counter").headers["x-latawiec-live"] == "1"
        clock = probe.get("/screens/clock")
        assert clock.headers["x-latawiec-refresh"] == "5"
        assert "x-latawiec-live" not in clock.headers


def test_refresh_pushes_a_fresh_render_to_subscribers() -> None:
    live_app, counter = _counter_app()

    # Sync handler: refresh crosses from the threadpool onto the loop.
    @live_app.action("bump")
    def bump(values: dict[str, str]) -> None:
        counter["n"] += 1
        live_app.refresh("counter")

    # Async handler: refresh schedules straight onto the running loop.
    @live_app.action("bump_async")
    async def bump_async(values: dict[str, str]) -> None:
        counter["n"] += 1
        live_app.refresh("counter")

    with TestClient(live_app) as probe, probe.websocket_connect("/ws/screens/counter") as socket:
        first = socket.receive_json()
        assert first["card"]["states"][0]["div"]["text"] == "Count: 0"

        probe.post("/actions/bump", json={})
        second = socket.receive_json()
        assert second["card"]["states"][0]["div"]["text"] == "Count: 1"

        probe.post("/actions/bump_async", json={})
        third = socket.receive_json()
        assert third["card"]["states"][0]["div"]["text"] == "Count: 2"


def test_refresh_before_serving_is_a_noop() -> None:
    live_app, _ = _counter_app()
    live_app.refresh("counter")  # must not raise


def test_a_screen_is_live_or_polled_never_both() -> None:
    conflicted = lt.Latawiec()
    try:
        conflicted.screen("x", live=True, refresh=5)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    try:
        conflicted.screen("y", refresh=0)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_a_broken_render_does_not_starve_other_subscribers() -> None:
    wobbly = lt.Latawiec()
    explode = {"on": False}

    @wobbly.screen("room/{id}", live=True)
    def room(ctx: lt.Context) -> lt.Component:
        if explode["on"] and ctx.params["id"] == "boom":
            raise RuntimeError("broken per-user data")
        return lt.Text(f"room {ctx.params['id']} {'hot' if explode['on'] else 'cold'}")

    @wobbly.action("arm")
    async def arm(values: dict[str, str]) -> None:
        explode["on"] = True
        wobbly.refresh("room/{id}")

    with (
        TestClient(wobbly) as probe,
        # boom subscribes first, so its broken render runs first.
        probe.websocket_connect("/ws/screens/room/boom") as broken,
        probe.websocket_connect("/ws/screens/room/ok") as fine,
    ):
        broken.receive_json()
        fine.receive_json()
        probe.post("/actions/arm", json={})
        pushed = fine.receive_json()["card"]["states"][0]["div"]["text"]
        assert pushed == "room ok hot"


def test_a_revoked_token_closes_the_live_subscription() -> None:
    guarded = lt.Latawiec()
    valid = {"sezam"}

    @guarded.auth
    def auth(token: str | None) -> str | None:
        return "pat" if token in valid else None

    @guarded.screen("inbox", live=True)
    def inbox(ctx: lt.Context) -> lt.Component:
        return lt.Text(f"Inbox of {ctx.user}")

    @guarded.action("poke", public=True)
    async def poke(values: dict[str, str]) -> None:
        guarded.refresh("inbox")

    with (
        TestClient(guarded) as probe,
        probe.websocket_connect(
            "/ws/screens/inbox", headers={"Authorization": "Bearer sezam"}
        ) as socket,
    ):
        socket.receive_json()
        valid.clear()
        probe.post("/actions/poke", json={})
        message = socket.receive()
        assert message["type"] == "websocket.close"
        assert message["code"] == 4401


def test_refresh_of_an_unknown_screen_raises() -> None:
    try:
        lt.Latawiec().refresh("nope")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass


def test_the_more_specific_template_wins() -> None:
    routed = lt.Latawiec()

    @routed.screen("{section}/{item}")
    def anything(ctx: lt.Context) -> lt.Component:
        return lt.Text(f"general {ctx.params['section']}/{ctx.params['item']}")

    @routed.screen("product/{id}")
    def product(ctx: lt.Context) -> lt.Component:
        return lt.Text(f"product {ctx.params['id']}")

    probe = TestClient(routed)
    div = probe.get("/screens/product/42").json()["card"]["states"][0]["div"]
    assert div["text"] == "product 42"
    div = probe.get("/screens/shop/42").json()["card"]["states"][0]["div"]
    assert div["text"] == "general shop/42"


def test_tied_templates_are_rejected_at_registration() -> None:
    routed = lt.Latawiec()

    @routed.screen("product/{id}")
    def product(ctx: lt.Context) -> lt.Component:
        return lt.Text("product")

    try:

        @routed.screen("{a}/edit")
        def edit(ctx: lt.Context) -> lt.Component:  # pragma: no cover
            return lt.Text("edit")

        raise AssertionError("expected ValueError")
    except ValueError as error:
        assert "product/{id}" in str(error)


def test_re_registering_a_screen_overwrites_it() -> None:
    routed = lt.Latawiec()

    @routed.screen("product/{id}")
    def old(ctx: lt.Context) -> lt.Component:
        return lt.Text("old")

    @routed.screen("product/{id}")
    def new(ctx: lt.Context) -> lt.Component:
        return lt.Text("new")

    div = TestClient(routed).get("/screens/product/1").json()["card"]["states"][0]["div"]
    assert div["text"] == "new"


def test_same_shape_templates_with_distinct_literals_coexist() -> None:
    routed = lt.Latawiec()

    @routed.screen("{a}/edit")
    def edit(ctx: lt.Context) -> lt.Component:
        return lt.Text(f"edit {ctx.params['a']}")

    # Same hole count, but 'edit' vs 'view' can never claim one path.
    @routed.screen("{b}/view")
    def view(ctx: lt.Context) -> lt.Component:
        return lt.Text(f"view {ctx.params['b']}")

    probe = TestClient(routed)
    assert probe.get("/screens/x/edit").json()["card"]["states"][0]["div"]["text"] == "edit x"
    assert probe.get("/screens/x/view").json()["card"]["states"][0]["div"]["text"] == "view x"


def test_well_known_serves_declared_app_links() -> None:
    linked = lt.Latawiec(
        app_links=lt.AppLinks(
            android_package="com.example.kiteshop",
            android_fingerprints=("AA:BB:CC",),
            ios_app_id="TEAM123.com.example.kiteshop",
        )
    )
    probe = TestClient(linked)

    assets = probe.get("/.well-known/assetlinks.json")
    assert assets.json() == [
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": "com.example.kiteshop",
                "sha256_cert_fingerprints": ["AA:BB:CC"],
            },
        }
    ]

    apple = probe.get("/.well-known/apple-app-site-association")
    assert apple.headers["content-type"].startswith("application/json")
    assert apple.json() == {
        "applinks": {
            "details": [{"appIDs": ["TEAM123.com.example.kiteshop"], "components": [{"/": "/*"}]}]
        }
    }


def test_well_known_is_404_for_the_undeclared_side() -> None:
    android_only = lt.Latawiec(
        app_links=lt.AppLinks(android_package="com.example.app", android_fingerprints=("aa:bb",))
    )
    probe = TestClient(android_only)
    assets = probe.get("/.well-known/assetlinks.json")
    assert assets.status_code == 200
    # Normalized for Android's verifier regardless of how it was typed.
    assert assets.json()[0]["target"]["sha256_cert_fingerprints"] == ["AA:BB"]
    assert probe.get("/.well-known/apple-app-site-association").status_code == 404

    bare = TestClient(lt.Latawiec())
    assert bare.get("/.well-known/assetlinks.json").status_code == 404
    assert bare.get("/.well-known/apple-app-site-association").status_code == 404


def test_an_android_package_without_fingerprints_is_rejected() -> None:
    try:
        lt.AppLinks(android_package="com.example.app")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_well_known_stays_public_under_auth() -> None:
    guarded = lt.Latawiec(
        app_links=lt.AppLinks(
            android_package="com.example.app",
            android_fingerprints=("AA:BB",),
            ios_app_id="T.com.example.app",
        )
    )

    @guarded.auth
    def reject_everyone(token: str | None) -> None:
        return None

    probe = TestClient(guarded)
    assert probe.get("/.well-known/assetlinks.json").status_code == 200
    assert probe.get("/.well-known/apple-app-site-association").status_code == 200


def test_manifest_fingerprint_rides_on_screens_and_moves_with_the_tabs() -> None:
    chrome = lt.Latawiec()

    @chrome.screen("home")
    def home() -> lt.Component:
        return lt.Text("hi")

    probe = TestClient(chrome)
    fingerprint = probe.get("/manifest").headers["x-latawiec-manifest"]
    assert probe.get("/screens/home").headers["x-latawiec-manifest"] == fingerprint

    # The chatbot use case: a tab appears at runtime.
    chrome.tabs = (lt.Tab("home", "Home"),)
    moved = probe.get("/manifest").headers["x-latawiec-manifest"]
    assert moved != fingerprint
    assert probe.get("/screens/home").headers["x-latawiec-manifest"] == moved
