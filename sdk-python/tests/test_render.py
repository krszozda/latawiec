import pytest

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


def test_submit_sends_variables_as_tap_time_expressions() -> None:
    card = lt.render(lt.Button("Send", on_tap=lt.Submit("sign up", send=("name", "email"))))

    action = card["card"]["states"][0]["div"]["actions"][0]
    assert action == {
        "log_id": "submit:sign up",
        "url": (
            "latawiec://submit?action=sign%20up&name=@{encodeUri(name)}&email=@{encodeUri(email)}"
        ),
    }


def test_text_input_binds_a_card_level_variable() -> None:
    card = lt.render(lt.TextInput("name", hint="Your name", initial="kite"))

    div = card["card"]["states"][0]["div"]
    assert div["type"] == "input"
    assert div["text_variable"] == "name"
    assert div["hint_text"] == "Your name"
    assert div["accessibility"] == {"description": "Your name"}
    assert card["card"]["variables"] == [{"type": "string", "name": "name", "value": "kite"}]


def test_nested_input_variables_are_hoisted_to_the_card() -> None:
    card = lt.render(lt.Column(lt.Row(lt.TextInput("a")), lt.TextInput("b", initial="x")))

    assert card["card"]["variables"] == [
        {"type": "string", "name": "a", "value": ""},
        {"type": "string", "name": "b", "value": "x"},
    ]


def test_conflicting_variable_initials_are_rejected() -> None:
    with pytest.raises(ValueError, match="conflicting initial values"):
        lt.render(lt.Column(lt.TextInput("name", initial="a"), lt.TextInput("name")))


def test_screens_without_inputs_declare_no_variables() -> None:
    card = lt.render(lt.Text("x"))

    assert "variables" not in card["card"]


def test_button_can_set_a_variable() -> None:
    card = lt.render(lt.Button("Reset", on_tap=lt.SetVariable("name", "")))

    action = card["card"]["states"][0]["div"]["actions"][0]
    assert action == {
        "log_id": "set:name",
        "typed": {
            "type": "set_variable",
            "variable_name": "name",
            "value": {"type": "string", "value": ""},
        },
    }


def test_render_wraps_root_in_card_envelope() -> None:
    card = lt.render(lt.Text("x"))

    assert set(card) == {"templates", "card"}
    assert card["card"]["states"][0]["state_id"] == 0


def test_style_covers_every_field() -> None:
    card = lt.render(
        lt.Text(
            "x",
            style=lt.Style(
                padding=8,
                margin=lt.Edges(top=4, left=16),
                width="fill",
                height=120,
                background="#FFF3E0",
                corner_radius=12,
                border="#FFB74D",
                align="center",
                align_vertical="bottom",
                alpha=0.5,
            ),
        )
    )

    div = card["card"]["states"][0]["div"]
    assert div == {
        "type": "text",
        "text": "x",
        "paddings": {"top": 8, "right": 8, "bottom": 8, "left": 8},
        "margins": {"top": 4, "right": 0, "bottom": 0, "left": 16},
        "width": {"type": "match_parent"},
        "height": {"type": "fixed", "value": 120},
        "background": [{"type": "solid", "color": "#FFF3E0"}],
        "border": {"corner_radius": 12, "stroke": {"color": "#FFB74D"}},
        "alignment_horizontal": "center",
        "alignment_vertical": "bottom",
        "alpha": 0.5,
    }


def test_unset_style_fields_keep_the_component_defaults() -> None:
    plain = lt.render(lt.Button("Buy", on_tap=lt.Navigate("checkout")))
    styled = lt.render(lt.Button("Buy", on_tap=lt.Navigate("checkout"), style=lt.Style(margin=8)))

    plain_div = plain["card"]["states"][0]["div"]
    styled_div = styled["card"]["states"][0]["div"]
    assert styled_div.pop("margins") == {"top": 8, "right": 8, "bottom": 8, "left": 8}
    assert styled_div == plain_div


def test_style_padding_overrides_input_defaults() -> None:
    card = lt.render(lt.TextInput("name", style=lt.Style(padding=0)))

    div = card["card"]["states"][0]["div"]
    assert div["paddings"] == {"top": 0, "right": 0, "bottom": 0, "left": 0}


def test_containers_take_a_style() -> None:
    card = lt.render(lt.Column(lt.Text("a"), style=lt.Style(background="#FFFFFF")))

    div = card["card"]["states"][0]["div"]
    assert div["background"] == [{"type": "solid", "color": "#FFFFFF"}]


def test_text_typography_options() -> None:
    card = lt.render(lt.Text("x", color="#37474F", weight="bold", align="right", line_height=28))

    div = card["card"]["states"][0]["div"]
    assert div == {
        "type": "text",
        "text": "x",
        "text_color": "#37474F",
        "font_weight": "bold",
        "text_alignment_horizontal": "right",
        "line_height": 28,
    }


def test_style_border_color_keeps_the_component_radius() -> None:
    card = lt.render(
        lt.Button("Buy", on_tap=lt.Navigate("checkout"), style=lt.Style(border="#000000"))
    )

    div = card["card"]["states"][0]["div"]
    assert div["border"] == {"corner_radius": 8, "stroke": {"color": "#000000"}}


def test_style_corner_radius_keeps_the_component_stroke() -> None:
    card = lt.render(lt.TextInput("name", style=lt.Style(corner_radius=4)))

    div = card["card"]["states"][0]["div"]
    assert div["border"] == {"corner_radius": 4, "stroke": {"color": "#B0BEC5"}}


def test_button_colors_are_customizable() -> None:
    card = lt.render(
        lt.Button("Buy", on_tap=lt.Navigate("checkout"), color="#00695C", text_color="#E0F2F1")
    )

    div = card["card"]["states"][0]["div"]
    assert div["background"] == [{"type": "solid", "color": "#00695C"}]
    assert div["text_color"] == "#E0F2F1"
