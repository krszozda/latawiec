import json
import sys
from pathlib import Path

import pytest

from latawiec.mcp import list_screens, render_screen


def test_list_screens_of_an_app_module() -> None:
    assert list_screens("app_fixture") == ["home"]


def test_render_screen_returns_divkit_card_json() -> None:
    payload = json.loads(render_screen("app_fixture", "home"))

    div = payload["card"]["states"][0]["div"]
    assert div["items"][0]["text"] == "Fixture"


def test_module_without_app_is_rejected() -> None:
    with pytest.raises(ValueError, match="defines no Latawiec app"):
        list_screens("latawiec")


APP_TEMPLATE = """\
import latawiec as lt

app = lt.Latawiec()


@app.screen("home")
def home() -> lt.Component:
    return lt.Column(lt.Text("{text}"))
"""


def test_render_screen_sees_module_edits(tmp_path: Path) -> None:
    app_file = tmp_path / "edited_app.py"
    app_file.write_text(APP_TEMPLATE.format(text="before"))
    sys.path.insert(0, str(tmp_path))
    try:
        assert "before" in render_screen("edited_app", "home")

        app_file.write_text(APP_TEMPLATE.format(text="after"))
        assert "after" in render_screen("edited_app", "home")
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("edited_app", None)
