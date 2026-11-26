"""The DSL reference: who can read it, and what it has to say."""

import subprocess
import sys

from fastapi.routing import APIRoute, APIWebSocketRoute

import latawiec as lt

# An app is written against these from the reference alone, so both ends
# are pinned: the server serves them, and the text names them.
CLIENT_ROUTES = (
    ("GET", "/manifest"),
    ("GET", "/screens/{name}"),
    ("WS", "/ws/screens/{name}"),
)


def served_routes() -> set[tuple[str, str]]:
    served: set[tuple[str, str]] = set()
    for route in lt.Latawiec().routes:
        # The path converter is a routing detail; a client sees "{name}".
        if isinstance(route, APIRoute):
            served |= {(method, route.path.replace(":path", "")) for method in route.methods or ()}
        elif isinstance(route, APIWebSocketRoute):
            served.add(("WS", route.path.replace(":path", "")))
    return served


def test_the_reference_names_every_endpoint_a_client_drives() -> None:
    text = lt.reference()
    served = served_routes()

    for method, path in CLIENT_ROUTES:
        assert (method, path) in served, f"the app no longer serves {method} {path}"
        assert f"{method} {path}" in text, f"the reference says nothing about {method} {path}"


def test_reading_the_reference_needs_no_mcp_extra() -> None:
    """`mcp` is installed in this environment, so the only way to test that
    the reference does without it is what an `import latawiec` reaches for.
    """
    probe = "import sys, latawiec; latawiec.reference(); print('mcp' in sys.modules)"

    done = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)

    assert done.stdout.strip() == "False"
