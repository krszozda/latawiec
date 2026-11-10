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


def test_share_puts_the_text_in_the_action_url() -> None:
    card = lt.render(lt.Button("Share", on_tap=lt.Share("Kites & more")))

    action = card["card"]["states"][0]["div"]["actions"][0]
    assert action == {"log_id": "share", "url": "latawiec://share?text=Kites%20%26%20more"}


def test_open_url_wraps_the_target() -> None:
    card = lt.render(lt.Button("Site", on_tap=lt.OpenUrl("https://example.com/a?b=1")))

    action = card["card"]["states"][0]["div"]["actions"][0]
    assert action == {
        "log_id": "open",
        "url": "latawiec://open?url=https%3A%2F%2Fexample.com%2Fa%3Fb%3D1",
    }


def test_copy_to_clipboard_is_a_typed_divkit_action() -> None:
    card = lt.render(lt.Button("Copy", on_tap=lt.CopyToClipboard("kite-42")))

    action = card["card"]["states"][0]["div"]["actions"][0]
    assert action == {
        "log_id": "copy",
        "typed": {"type": "copy_to_clipboard", "content": {"type": "text", "value": "kite-42"}},
    }


def test_haptic_is_a_typed_divkit_action() -> None:
    card = lt.render(lt.Button("Buzz", on_tap=lt.Haptic("success")))

    action = card["card"]["states"][0]["div"]["actions"][0]
    assert action == {
        "log_id": "haptic:success",
        "typed": {"type": "haptic", "feedback": "success"},
    }


def test_sign_out_names_the_landing_screen_only_when_given() -> None:
    card = lt.render(lt.Button("Leave", on_tap=lt.SignOut()))
    action = card["card"]["states"][0]["div"]["actions"][0]
    assert action == {"log_id": "signout", "url": "latawiec://signout"}

    card = lt.render(lt.Button("Leave", on_tap=lt.SignOut(screen="bye bye")))
    action = card["card"]["states"][0]["div"]["actions"][0]
    assert action == {"log_id": "signout", "url": "latawiec://signout?screen=bye%20bye"}


def test_request_location_carries_the_variable_and_the_follow_up_action() -> None:
    card = lt.render(lt.Button("Locate", on_tap=lt.RequestLocation("spot")))
    action = card["card"]["states"][0]["div"]["actions"][0]
    assert action == {"log_id": "locate", "url": "latawiec://locate?variable=spot"}

    card = lt.render(lt.Button("Locate", on_tap=lt.RequestLocation("spot", then="near me")))
    action = card["card"]["states"][0]["div"]["actions"][0]
    assert action == {
        "log_id": "locate",
        "url": "latawiec://locate?variable=spot&action=near%20me",
    }


def test_request_location_declares_the_variable_it_writes_into() -> None:
    # No component carries this variable, yet a sibling Text must be able to
    # read it the moment the fix lands.
    card = lt.render(
        lt.Column(
            lt.Text("@{spot}"),
            lt.Button("Locate", on_tap=lt.RequestLocation("spot")),
        )
    )

    assert card["card"]["variables"] == [{"type": "string", "name": "spot", "value": ""}]


def test_request_location_writes_into_an_existing_control_variable() -> None:
    # Dropping the fix into a search box the user can still edit: the input's
    # declaration wins, so its hint and initial value survive.
    card = lt.render(
        lt.Column(
            lt.TextInput("spot", initial="Warsaw"),
            lt.Button("Use my location", on_tap=lt.RequestLocation("spot")),
        )
    )

    assert card["card"]["variables"] == [{"type": "string", "name": "spot", "value": "Warsaw"}]


def test_unlock_gates_a_submit_behind_the_device_check() -> None:
    card = lt.render(
        lt.Button("Pay", on_tap=lt.Unlock("pay", send=("amount",), reason="Confirm the payment"))
    )

    action = card["card"]["states"][0]["div"]["actions"][0]
    assert action == {
        "log_id": "unlock:pay",
        "url": (
            "latawiec://unlock?action=pay&reason=Confirm%20the%20payment"
            "&amount=@{encodeUri(amount)}"
        ),
    }


def test_unlock_refuses_input_the_shells_cannot_carry() -> None:
    # Both platforms reject an empty prompt title, iOS by throwing.
    with pytest.raises(ValueError, match="reason"):
        lt.Unlock("pay", reason="")

    # The URL already carries these names, so a variable of the same name
    # would be read as the prompt text and never reach the handler.
    with pytest.raises(ValueError, match="reason"):
        lt.Unlock("transfer", send=("reason",))
    with pytest.raises(ValueError, match="action"):
        lt.Submit("transfer", send=("action",))


def test_map_hands_the_shells_everything_they_draw() -> None:
    card = lt.render(
        lt.Map(52.2297, 21.0122, zoom=12, height=320, markers=(lt.Marker(50.06, 19.94, "Kraków"),))
    )

    div = card["card"]["states"][0]["div"]
    assert div["type"] == "custom"
    assert div["custom_type"] == "latawiec_map"
    assert div["height"] == {"type": "fixed", "value": 320}
    assert div["custom_props"] == {
        "latitude": 52.2297,
        "longitude": 21.0122,
        "zoom": 12,
        # Empty means "whatever the platform draws by default".
        "tiles": "",
        "markers": [{"latitude": 50.06, "longitude": 19.94, "label": "Kraków"}],
    }


def test_map_refuses_coordinates_that_are_not_on_earth() -> None:
    with pytest.raises(ValueError, match="latitude"):
        lt.Map(91, 0)
    with pytest.raises(ValueError, match="longitude"):
        lt.Map(0, -181)
    # Tile pyramids stop here; asking for more draws nothing at all.
    with pytest.raises(ValueError, match="zoom"):
        lt.Map(0, 0, zoom=21)


def test_a_tap_can_run_several_actions_in_order() -> None:
    card = lt.render(lt.Button("Send", on_tap=(lt.Haptic(), lt.Navigate("done"))))

    actions = card["card"]["states"][0]["div"]["actions"]
    assert [a["log_id"] for a in actions] == ["haptic:light", "navigate:done"]


def test_text_input_binds_a_card_level_variable() -> None:
    card = lt.render(lt.TextInput("name", hint="Your name", initial="kite"))

    div = card["card"]["states"][0]["div"]
    assert div["type"] == "input"
    assert div["text_variable"] == "name"
    assert div["hint_text"] == "Your name"
    assert div["accessibility"] == {"description": "Your name"}
    assert card["card"]["variables"] == [{"type": "string", "name": "name", "value": "kite"}]


def test_password_input_uses_the_password_keyboard() -> None:
    card = lt.render(lt.TextInput("code", password=True))

    div = card["card"]["states"][0]["div"]
    assert div["keyboard_type"] == "password"


def test_nested_input_variables_are_hoisted_to_the_card() -> None:
    card = lt.render(lt.Column(lt.Row(lt.TextInput("a")), lt.TextInput("b", initial="x")))

    assert card["card"]["variables"] == [
        {"type": "string", "name": "a", "value": ""},
        {"type": "string", "name": "b", "value": "x"},
    ]


def test_conflicting_variable_initials_are_rejected() -> None:
    with pytest.raises(ValueError, match="conflicting types or initial values"):
        lt.render(lt.Column(lt.TextInput("name", initial="a"), lt.TextInput("name")))


def test_conflicting_variable_types_are_rejected() -> None:
    with pytest.raises(ValueError, match="conflicting types or initial values"):
        lt.render(lt.Column(lt.TextInput("flag"), lt.Switch("flag")))


def test_switch_binds_a_boolean_variable() -> None:
    card = lt.render(lt.Switch("dark", initial=True))

    div = card["card"]["states"][0]["div"]
    assert div == {
        "type": "switch",
        "is_on_variable": "dark",
        "width": {"type": "wrap_content"},
    }
    assert card["card"]["variables"] == [{"type": "boolean", "name": "dark", "value": True}]


def test_select_renders_options_and_binds_a_string_variable() -> None:
    card = lt.render(
        lt.Select("size", options=("Small", lt.Option("Medium", "m")), hint="Size", initial="m")
    )

    div = card["card"]["states"][0]["div"]
    assert div == {
        "type": "select",
        "value_variable": "size",
        "options": [
            {"text": "Small", "value": "Small"},
            {"text": "Medium", "value": "m"},
        ],
        "hint_text": "Size",
        "accessibility": {"description": "Size"},
        "paddings": {"top": 12, "right": 16, "bottom": 12, "left": 16},
        "border": {"corner_radius": 8, "stroke": {"color": "#B0BEC5"}},
    }
    assert card["card"]["variables"] == [{"type": "string", "name": "size", "value": "m"}]


def test_select_keeps_an_explicit_empty_option_value() -> None:
    card = lt.render(lt.Select("size", options=(lt.Option("None", ""),)))

    options = card["card"]["states"][0]["div"]["options"]
    assert options == [{"text": "None", "value": ""}]


def test_slider_draws_thumb_and_tracks_and_binds_an_integer_variable() -> None:
    card = lt.render(lt.Slider("volume", min=1, max=10, color="#00695C"))

    div = card["card"]["states"][0]["div"]
    assert div == {
        "type": "slider",
        "thumb_value_variable": "volume",
        "min_value": 1,
        "max_value": 10,
        "thumb_style": {
            "type": "shape_drawable",
            "color": "#00695C",
            "shape": {
                "type": "rounded_rectangle",
                "item_width": {"type": "fixed", "value": 24},
                "item_height": {"type": "fixed", "value": 24},
                "corner_radius": {"type": "fixed", "value": 12},
            },
        },
        "track_active_style": {
            "type": "shape_drawable",
            "color": "#00695C",
            "shape": {
                "type": "rounded_rectangle",
                "item_height": {"type": "fixed", "value": 4},
            },
        },
        "track_inactive_style": {
            "type": "shape_drawable",
            "color": "#B0BEC5",
            "shape": {
                "type": "rounded_rectangle",
                "item_height": {"type": "fixed", "value": 4},
            },
        },
    }
    assert card["card"]["variables"] == [{"type": "integer", "name": "volume", "value": 1}]


def test_slider_initial_overrides_the_min_default() -> None:
    card = lt.render(lt.Slider("volume", min=0, max=10, initial=7))

    assert card["card"]["variables"] == [{"type": "integer", "name": "volume", "value": 7}]


def test_mixed_control_variables_hoist_in_document_order() -> None:
    card = lt.render(
        lt.Column(
            lt.Switch("dark"),
            lt.Row(lt.TextInput("name")),
            lt.Slider("volume", min=2),
            lt.Select("size", options=("S",)),
        )
    )

    assert card["card"]["variables"] == [
        {"type": "boolean", "name": "dark", "value": False},
        {"type": "string", "name": "name", "value": ""},
        {"type": "integer", "name": "volume", "value": 2},
        {"type": "string", "name": "size", "value": ""},
    ]


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


def test_gallery_scrolls_vertically_by_default() -> None:
    card = lt.render(lt.Gallery(lt.Text("a"), lt.Text("b"), spacing=12))

    div = card["card"]["states"][0]["div"]
    assert div == {
        "type": "gallery",
        "orientation": "vertical",
        "item_spacing": 12,
        "items": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}],
    }


def test_gallery_horizontal_emits_the_orientation() -> None:
    card = lt.render(lt.Gallery(lt.Text("a"), horizontal=True))

    div = card["card"]["states"][0]["div"]
    assert div["orientation"] == "horizontal"


def test_grid_lays_children_in_columns() -> None:
    card = lt.render(lt.Grid(lt.Text("a"), lt.Text("b"), lt.Text("c"), columns=2))

    div = card["card"]["states"][0]["div"]
    wrap = {"type": "wrap_content"}
    assert div == {
        "type": "grid",
        "column_count": 2,
        "items": [
            {"type": "text", "text": "a", "width": wrap},
            {"type": "text", "text": "b", "width": wrap},
            {"type": "text", "text": "c", "width": wrap},
        ],
    }


def test_grid_keeps_an_explicit_child_width() -> None:
    card = lt.render(lt.Grid(lt.Text("a", style=lt.Style(width=80)), columns=1))

    item = card["card"]["states"][0]["div"]["items"][0]
    assert item["width"] == {"type": "fixed", "value": 80}


def test_separator_draws_a_colored_rule() -> None:
    card = lt.render(lt.Separator(color="#000000"))

    div = card["card"]["states"][0]["div"]
    assert div == {"type": "separator", "delimiter_style": {"color": "#000000"}}


def test_spacer_is_a_transparent_separator_of_fixed_size() -> None:
    card = lt.render(lt.Spacer(height=16))

    div = card["card"]["states"][0]["div"]
    assert div == {
        "type": "separator",
        "height": {"type": "fixed", "value": 16},
        "delimiter_style": {"color": "#00000000"},
    }


def test_spacer_without_a_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="height or a width"):
        lt.render(lt.Spacer())


def test_control_variables_inside_collections_are_hoisted() -> None:
    card = lt.render(lt.Gallery(lt.Grid(lt.Switch("dark"), columns=1)))

    assert card["card"]["variables"] == [{"type": "boolean", "name": "dark", "value": False}]


def test_stack_overlaps_children() -> None:
    card = lt.render(lt.Stack(lt.Image("https://x/photo.png"), lt.Text("badge")))

    div = card["card"]["states"][0]["div"]
    assert div["type"] == "container"
    assert div["orientation"] == "overlap"
    assert [item["type"] for item in div["items"]] == ["image", "text"]


def test_pager_pages_full_width_and_links_to_indicator() -> None:
    card = lt.render(
        lt.Column(
            lt.Pager(lt.Text("one"), lt.Text("two"), id="intro", spacing=8),
            lt.Indicator("intro", color="#00695C"),
        )
    )

    pager, indicator = card["card"]["states"][0]["div"]["items"]
    assert pager == {
        "type": "pager",
        "id": "intro",
        "item_spacing": {"type": "fixed", "value": 8},
        "layout_mode": {"type": "percentage", "page_width": {"type": "percentage", "value": 100.0}},
        "items": [{"type": "text", "text": "one"}, {"type": "text", "text": "two"}],
    }
    assert indicator == {
        "type": "indicator",
        "pager_id": "intro",
        "active_item_color": "#00695C",
        "inactive_item_color": "#B0BEC5",
    }


def test_tabs_pair_titles_with_content() -> None:
    card = lt.render(lt.Tabs(("One", lt.Text("a")), ("Two", lt.Text("b"))))

    div = card["card"]["states"][0]["div"]
    assert div == {
        "type": "tabs",
        "items": [
            {"title": "One", "div": {"type": "text", "text": "a"}},
            {"title": "Two", "div": {"type": "text", "text": "b"}},
        ],
    }


def test_video_flags_are_emitted_only_when_set() -> None:
    plain = lt.render(lt.Video("https://x/clip.mp4"))["card"]["states"][0]["div"]
    assert plain == {
        "type": "video",
        "video_sources": [
            {"type": "video_source", "url": "https://x/clip.mp4", "mime_type": "video/mp4"}
        ],
    }

    looped = lt.render(lt.Video("https://x/clip.mp4", autoplay=True, loop=True, muted=True))
    div = looped["card"]["states"][0]["div"]
    assert div["autostart"] is True
    assert div["repeatable"] is True
    assert div["muted"] is True


def test_gif_image_renders_to_divkit_gif() -> None:
    card = lt.render(lt.GifImage("https://x/anim.gif"))

    div = card["card"]["states"][0]["div"]
    assert div == {"type": "gif", "gif_url": "https://x/anim.gif"}


def test_variables_hoist_through_stack_pager_and_tabs() -> None:
    card = lt.render(
        lt.Stack(
            lt.Pager(lt.Switch("dark"), id="p"),
            lt.Tabs(("T", lt.TextInput("name"))),
        )
    )

    assert card["card"]["variables"] == [
        {"type": "boolean", "name": "dark", "value": False},
        {"type": "string", "name": "name", "value": ""},
    ]


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


def test_appearance_transitions_carry_every_trigger() -> None:
    card = lt.render(
        lt.Text(
            "hi",
            style=lt.Style(
                appear=lt.Fade(300),
                disappear=lt.Slide(edge="left", duration=200, delay=50),
                move=150,
            ),
        )
    )

    div = card["card"]["states"][0]["div"]
    assert div["transition_in"] == {"type": "fade", "duration": 300}
    assert div["transition_out"] == {
        "type": "slide",
        "edge": "left",
        "duration": 200,
        "start_delay": 50,
    }
    assert div["transition_change"] == {"type": "change_bounds", "duration": 150}
    # data_change included: live refreshes animate too.
    assert div["transition_triggers"] == ["data_change", "state_change", "visibility_change"]


def test_grow_and_the_tap_feedback_render() -> None:
    card = lt.render(
        lt.Button(
            "Go",
            on_tap=lt.Navigate("x"),
            tap_animation="none",
            style=lt.Style(appear=lt.Grow(250)),
        )
    )

    div = card["card"]["states"][0]["div"]
    assert div["transition_in"] == {"type": "scale", "duration": 250}
    assert div["action_animation"] == {"name": "no_animation"}


def test_tap_feedback_names_pass_through_and_slide_pins_its_default_edge() -> None:
    card = lt.render(
        lt.Button(
            "Go",
            on_tap=lt.Navigate("x"),
            tap_animation="scale",
            style=lt.Style(appear=lt.Slide()),
        )
    )

    div = card["card"]["states"][0]["div"]
    assert div["action_animation"] == {"name": "scale"}
    assert div["transition_in"] == {"type": "slide", "duration": 300, "edge": "bottom"}


def test_image_picker_declares_its_variable_and_toggles_preview() -> None:
    card = lt.render(lt.ImagePicker("photo", label="Add one", height=120))

    assert card["card"]["variables"] == [{"type": "string", "name": "photo", "value": ""}]
    div = card["card"]["states"][0]["div"]
    assert div["actions"] == [
        {"log_id": "pick:gallery", "url": "latawiec://pick?variable=photo&source=gallery"}
    ]
    placeholder, preview = div["items"]
    assert placeholder["text"] == "Add one"
    assert placeholder["visibility"] == "@{photo == '' ? 'visible' : 'gone'}"
    assert preview["image_url"] == "@{photo}"
    assert preview["visibility"] == "@{photo != '' ? 'visible' : 'gone'}"
    assert preview["height"] == {"type": "fixed", "value": 120}


def test_image_picker_can_ask_for_the_camera_instead() -> None:
    card = lt.render(lt.ImagePicker("photo", source="camera"))

    div = card["card"]["states"][0]["div"]
    assert div["actions"] == [
        {"log_id": "pick:camera", "url": "latawiec://pick?variable=photo&source=camera"}
    ]
    # The placeholder says what the tap will do, without being told.
    assert div["items"][0]["text"] == "Take a photo"


def test_load_more_fires_its_action_on_sight() -> None:
    card = lt.render(lt.LoadMore("page", label="More…"))

    div = card["card"]["states"][0]["div"]
    assert div["text"] == "More…"
    assert div["visibility_actions"] == [
        {
            "log_id": "more:page",
            "url": "latawiec://submit?action=page",
            "log_limit": 0,
            "visibility_duration": 100,
            "visibility_percentage": 1,
        }
    ]
