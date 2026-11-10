"""The showcase is the app people read first, so it must not rot.

These do not pin its content — that would make every edit a test change.
They pin that every screen it advertises still renders, and that it keeps
demonstrating the whole surface, which is the one thing it is for.
"""

from fastapi.testclient import TestClient

from examples.showcase import app

client = TestClient(app)


def screens() -> dict[str, str]:
    """Every screen as the shell receives it: real JSON, not a repr.

    Screens with a path parameter are skipped — there is no id to put in
    one, and the showcase has none today.
    """
    plain = [name for name in app.screen_names if "{" not in name]
    answers = {name: client.get(f"/screens/{name}") for name in plain}
    for name, answer in answers.items():
        assert answer.status_code == 200, f"{name} answered HTTP {answer.status_code}"
    return {name: answer.text for name, answer in answers.items()}


def test_every_screen_still_renders() -> None:
    for name, card in screens().items():
        assert '"states":[{"div":' in card, f"{name} rendered an empty card"


def test_the_tabs_point_at_screens_that_exist() -> None:
    for tab in app.tabs:
        assert tab.screen in app.screen_names, f"the {tab.title} tab points nowhere"


def test_it_still_shows_what_it_claims_to() -> None:
    # The showcase is the first thing anyone reads, so every piece it
    # advertises has to still be in it. Auth, push and deep links are
    # deliberately absent — they have examples of their own.
    shown = "".join(screens().values())

    for feature, needle in {
        "navigation": "latawiec://navigate",
        "a server action": "latawiec://submit",
        "the clipboard": "copy_to_clipboard",
        "sharing": "latawiec://share",
        "opening a link": "latawiec://open",
        "haptics": "haptic",
        "the device unlock": "latawiec://unlock",
        "location": "latawiec://locate",
        "the gallery": "source=gallery",
        "the camera": "source=camera",
        "a purchase": "latawiec://buy",
        "pagination": "more:more",
        "setting a variable": "set_variable",
        "an image": '"type":"image"',
        "a pager's dots": '"type":"indicator"',
        "a separator": '"type":"separator"',
        "a map": "latawiec_map",
        "video": '"type":"video"',
        "an animation": "transition_in",
        "a pager": '"type":"pager"',
        "a grid": '"type":"grid"',
        "a slider": '"type":"slider"',
        "a switch": '"type":"switch"',
        "a select": '"type":"select"',
        "a text input": '"type":"input"',
    }.items():
        assert needle in shown, f"the showcase no longer demonstrates {feature}"


def test_the_live_and_refreshable_screens_tell_the_shell_so() -> None:
    # What makes the Moving tab worth reading is that these are not plain
    # screens; a refactor that quietly dropped the flags would gut it, and
    # the shell learns about them from these headers.
    assert client.get("/screens/moving").headers.get("X-Latawiec-Live") == "1"
    assert client.get("/screens/feed").headers.get("X-Latawiec-Live") == "1"
    assert client.get("/screens/pulled").headers.get("X-Latawiec-Refreshable") == "1"


def test_the_pull_to_refresh_screen_can_actually_be_pulled() -> None:
    # The gesture only exists in production mode: in the dev loop every
    # screen rides a WebSocket and the header never reaches the shell.
    assert client.get("/manifest").json()["dev"] is False


def test_the_purchase_handler_does_not_model_trusting_the_client() -> None:
    # The shells send only the receipt, and an example that granted what
    # the request named would teach the dangerous shape.
    card = client.get("/screens/shop").text
    assert "latawiec://buy?product=kite.one&action=granted&consumable=1" in card

    answered = client.post(
        "/actions/granted",
        json={"receipt": "x" * 40},
        headers={"X-Latawiec-Platform": "ios"},
    )

    assert answered.status_code == 200
    # It reports that a receipt arrived and says to verify it, rather than
    # granting whatever the request named.
    assert "verify it" in client.get("/screens/shop", headers={"X-Latawiec-Platform": "ios"}).text
