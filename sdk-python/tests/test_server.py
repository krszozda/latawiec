from fastapi.testclient import TestClient

import latawiec as lt

app = lt.Latawiec()


@app.screen("home")
def home() -> lt.Component:
    return lt.Column(lt.Text("Hello"))


client = TestClient(app)


def test_screen_endpoint_returns_rendered_card() -> None:
    response = client.get("/screens/home")

    assert response.status_code == 200
    div = response.json()["card"]["states"][0]["div"]
    assert div["items"][0]["text"] == "Hello"


def test_unknown_screen_is_404() -> None:
    assert client.get("/screens/nope").status_code == 404


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
