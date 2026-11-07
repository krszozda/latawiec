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
