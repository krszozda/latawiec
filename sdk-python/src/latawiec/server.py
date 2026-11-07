from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from latawiec.components import Component, Navigate, render

ScreenBuilder = Callable[[], Component]
AuthHandler = Callable[[str | None], bool]

# WebSocket close codes in the app-defined 4000-4999 range, echoing HTTP.
NO_SUCH_SCREEN = 4404
NOT_AUTHORIZED = 4401


@dataclass(frozen=True)
class Tab:
    """One destination of the shells' native bottom bar."""

    screen: str
    title: str
    icon: str | None = None
    """Image path the shell resolves against the server, e.g. "/assets/home.png"."""


@dataclass(frozen=True)
class Theme:
    """Colors the shells apply to their native chrome."""

    accent: str = "#2962FF"


@dataclass(frozen=True)
class Grant:
    """Sign-in result: the shell stores the token and navigates on.

    Every later request carries it as `Authorization: Bearer <token>`.
    """

    token: str
    screen: str


ActionHandler = Callable[[dict[str, str]], Navigate | Grant | None]


def _bearer(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    return token if scheme.lower() == "bearer" and token else None


class Latawiec(FastAPI):
    """An ASGI app that serves Latawiec screens; run it like any FastAPI app."""

    def __init__(
        self,
        *,
        tabs: Sequence[Tab] = (),
        theme: Theme | None = None,
        login: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.tabs = tuple(tabs)
        self.theme = theme or Theme()
        self.login = login
        """Screen the shells show when the server answers 401/4401."""
        self._auth: AuthHandler | None = None
        self._screens: dict[str, ScreenBuilder] = {}
        self._actions: dict[str, ActionHandler] = {}
        self._public_screens: set[str] = set()
        self._public_actions: set[str] = set()
        self.add_api_route("/manifest", self._manifest)
        self.add_api_route("/screens/{name}", self._screen_payload)
        self.add_api_route("/actions/{name}", self._action_result, methods=["POST"])
        self.add_api_websocket_route("/ws/screens/{name}", self._screen_socket)

    def assets(self, directory: str) -> None:
        """Serve a directory of static files (tab icons, images) under /assets."""
        self.mount("/assets", StaticFiles(directory=directory), name="assets")

    def auth(self, handler: AuthHandler) -> AuthHandler:
        """Register the token check; it gets the bearer token (or None).

        Once registered, screens and actions answer 401 (sockets close with
        4401) unless the handler accepts the token or they were registered
        with public=True. The manifest and /assets stay public: the shell
        needs them to show the login screen in the first place.
        """
        self._auth = handler
        return handler

    def screen(
        self, name: str, *, public: bool = False
    ) -> Callable[[ScreenBuilder], ScreenBuilder]:
        def register(builder: ScreenBuilder) -> ScreenBuilder:
            self._screens[name] = builder
            if public:
                self._public_screens.add(name)
            return builder

        return register

    def action(
        self, name: str, *, public: bool = False
    ) -> Callable[[ActionHandler], ActionHandler]:
        """Register the handler that a Submit(name, ...) button posts to."""

        def register(handler: ActionHandler) -> ActionHandler:
            self._actions[name] = handler
            if public:
                self._public_actions.add(name)
            return handler

        return register

    @property
    def screen_names(self) -> tuple[str, ...]:
        return tuple(self._screens)

    def render_screen(self, name: str) -> dict[str, Any]:
        """Render a registered screen to the DivKit card payload a shell renders."""
        builder = self._screens.get(name)
        if builder is None:
            raise KeyError(f"no screen named {name!r}")
        return render(builder())

    def _rejects(self, name: str, public: set[str], authorization: str | None) -> bool:
        if self._auth is None or name in public:
            return False
        return not self._auth(_bearer(authorization))

    async def _manifest(self) -> dict[str, Any]:
        """App-level chrome the shells read once at startup: tabs, theme, login."""
        return {
            "tabs": [
                {"screen": tab.screen, "title": tab.title, "icon": tab.icon} for tab in self.tabs
            ],
            "theme": {"accent": self.theme.accent},
            "login": self.login,
        }

    async def _screen_payload(
        self,
        name: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        if self._rejects(name, self._public_screens, authorization):
            raise HTTPException(
                status_code=401,
                detail="not authorized",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            return self.render_screen(name)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"no screen named {name!r}") from None

    async def _action_result(
        self,
        name: str,
        values: dict[str, str],
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, str | None]:
        if self._rejects(name, self._public_actions, authorization):
            raise HTTPException(
                status_code=401,
                detail="not authorized",
                headers={"WWW-Authenticate": "Bearer"},
            )
        handler = self._actions.get(name)
        if handler is None:
            raise HTTPException(status_code=404, detail=f"no action named {name!r}")
        result = handler(values)
        if isinstance(result, Grant):
            return {"navigate": result.screen, "token": result.token}
        return {"navigate": result.screen if result else None}

    async def _screen_socket(self, websocket: WebSocket, name: str) -> None:
        """Send the screen once, then hold the socket open.

        Live reload rides on this: `uvicorn --reload` restarts the process on
        every code change, the socket drops, and the shell reconnects to get
        the fresh screen.
        """
        await websocket.accept()
        if self._rejects(name, self._public_screens, websocket.headers.get("authorization")):
            await websocket.close(code=NOT_AUTHORIZED, reason="not authorized")
            return
        try:
            payload = self.render_screen(name)
        except KeyError:
            await websocket.close(code=NO_SUCH_SCREEN, reason=f"no screen named {name!r}")
            return
        await websocket.send_json(payload)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
