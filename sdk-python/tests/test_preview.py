"""The /preview page: what it hands the browser, and who gets it at all."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import latawiec as lt

DATA_TAG = re.compile(r'<script id="data" type="application/json">(.*?)</script>', re.DOTALL)


def page_payload(body: str) -> str:
    match = DATA_TAG.search(body)
    assert match is not None, "the page carries no data tag"
    return match.group(1)


def page_data(body: str) -> dict[str, object]:
    return json.loads(page_payload(body))


def test_preview_lists_the_screens_the_app_registered() -> None:
    app = lt.Latawiec()

    @app.screen("home")
    def home() -> lt.Component:
        return lt.Column(lt.Text("Hello"))

    @app.screen("product/{id}")
    def product(ctx: lt.Context) -> lt.Component:
        return lt.Column(lt.Text(ctx.params["id"]))

    response = TestClient(app).get("/preview")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    # Templates as registered: the page offers them for filling in, not
    # as a path it could fetch.
    assert page_data(response.text)["screens"] == ["home", "product/{id}"]


def test_preview_carries_the_theme_background_and_login_screen() -> None:
    app = lt.Latawiec(theme=lt.Theme(accent="#00695C", background="#101010"), login="signin")

    data = page_data(TestClient(app).get("/preview").text)

    assert data["background"] == "#101010"
    assert data["login"] == "signin"


def test_a_deployed_app_serves_no_preview() -> None:
    app = lt.Latawiec(dev=False)

    assert TestClient(app).get("/preview").status_code == 404


def test_a_prod_mode_app_can_ask_for_the_preview_back() -> None:
    app = lt.Latawiec(dev=False, preview=True)

    assert TestClient(app).get("/preview").status_code == 200


def test_a_dev_app_can_turn_the_preview_off() -> None:
    app = lt.Latawiec(preview=False)

    assert TestClient(app).get("/preview").status_code == 404


def test_the_preview_stays_out_of_the_api_the_shells_read() -> None:
    app = lt.Latawiec()

    schema = TestClient(app).get("/openapi.json").json()

    assert "/manifest" in schema["paths"]
    assert "/preview" not in schema["paths"]


def test_a_screen_name_cannot_escape_the_data_tag() -> None:
    app = lt.Latawiec()

    @app.screen("</script><script>stolen()</script>")
    def sneaky() -> lt.Component:
        return lt.Column(lt.Text("Hello"))

    # "<!--<script" is the other way out: it makes the tag's own end tag
    # stop closing it, and the page's script is swallowed as text.
    @app.screen("<!--<script>")
    def sneakier() -> lt.Component:
        return lt.Column(lt.Text("Hello"))

    body = TestClient(app).get("/preview").text

    # No name brings a "<" along, so none of it is markup; the names
    # still reach the page intact.
    assert "<" not in page_payload(body)
    assert page_data(body)["screens"] == ["</script><script>stolen()</script>", "<!--<script>"]


SHELL_PINS = {
    "shell-android/app/build.gradle.kts": re.compile(r"com\.yandex\.div:div:([\d.]+)"),
    # Anchored to the package, or another SPM dependency's version would do.
    "shell-ios/project.yml": re.compile(r"divkit-ios\s+exactVersion:\s*([\d.]+)"),
}


def test_the_preview_draws_with_the_divkit_version_the_shells_carry() -> None:
    """On another version it stands in for something the phones do not run,
    and a floating tag would move it without a commit."""
    body = TestClient(lt.Latawiec()).get("/preview").text

    urls = set(re.findall(r"https://cdn\.jsdelivr\.net/npm/[^\"\s)]+", body))
    assert urls, "the page loads no renderer"
    for url in urls:
        assert re.search(r"@\d+\.\d+\.\d+/", url), f"{url} is not pinned to a version"
    # The page runs on the same origin as the developer's session, so each
    # file it takes from the CDN is checked against a hash.
    assert len(re.findall(r"sha384-", body)) == len(urls)
    drawn = re.search(r"@divkitframework/divkit@([\d.]+)/", body)
    assert drawn is not None

    repo = Path(__file__).resolve().parents[2]
    for name, pin in SHELL_PINS.items():
        source = repo / name
        if not source.exists():
            pytest.skip(f"{name} is not next to this package")
        carried = pin.search(source.read_text())
        assert carried is not None, f"no DivKit version found in {name}"
        assert carried.group(1) == drawn.group(1), (
            f"the preview draws with DivKit {drawn.group(1)}, {name} carries {carried.group(1)}"
        )
