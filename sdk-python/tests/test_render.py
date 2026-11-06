import latawiec as lt


def test_text_renders_to_divkit_text() -> None:
    card = lt.render(lt.Text("Hello", size=24))

    div = card["card"]["states"][0]["div"]
    assert div == {"type": "text", "text": "Hello", "font_size": 24}


def test_text_omits_unset_size() -> None:
    card = lt.render(lt.Text("Hello"))

    div = card["card"]["states"][0]["div"]
    assert div == {"type": "text", "text": "Hello"}


def test_column_nests_children_vertically() -> None:
    card = lt.render(lt.Column(lt.Text("a"), lt.Text("b")))

    div = card["card"]["states"][0]["div"]
    assert div["type"] == "container"
    assert div["orientation"] == "vertical"
    assert [item["text"] for item in div["items"]] == ["a", "b"]


def test_row_lays_children_side_by_side() -> None:
    card = lt.render(lt.Row(lt.Text("a"), lt.Text("b")))

    div = card["card"]["states"][0]["div"]
    assert div["type"] == "container"
    assert div["orientation"] == "horizontal"


def test_image_renders_to_divkit_image() -> None:
    card = lt.render(lt.Image("https://example.com/kite.png"))

    div = card["card"]["states"][0]["div"]
    assert div == {"type": "image", "image_url": "https://example.com/kite.png"}


def test_button_is_tappable_text_with_navigate_action() -> None:
    card = lt.render(lt.Button("Buy", on_tap=lt.Navigate("checkout")))

    div = card["card"]["states"][0]["div"]
    assert div["type"] == "text"
    assert div["text"] == "Buy"
    assert div["actions"] == [
        {"log_id": "navigate:checkout", "url": "latawiec://navigate?screen=checkout"}
    ]


def test_navigate_percent_encodes_screen_name() -> None:
    card = lt.render(lt.Button("Go", on_tap=lt.Navigate("a&b c")))

    action = card["card"]["states"][0]["div"]["actions"][0]
    assert action["url"] == "latawiec://navigate?screen=a%26b%20c"


def test_render_wraps_root_in_card_envelope() -> None:
    card = lt.render(lt.Text("x"))

    assert set(card) == {"templates", "card"}
    assert card["card"]["states"][0]["state_id"] == 0
