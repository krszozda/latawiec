from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from latawiec.components import Component, Navigate, render

ScreenBuilder = Callable[[], Component]
ActionHandler = Callable[[dict[str, str]], Navigate | None]

# WebSocket close code in the app-defined 4000-4999 range, echoing HTTP 404.
NO_SUCH_SCREEN = 4404


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


class Latawiec(FastAPI):
    """An ASGI app that serves Latawiec screens; run it like any FastAPI app."""

    def __init__(
        self,
        *,
        tabs: Sequence[Tab] = (),
        theme: Theme | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.tabs = tuple(tabs)
        self.theme = theme or Theme()
        self._screens: dict[str, ScreenBuilder] = {}
        self._actions: dict[str, ActionHandler] = {}
        self.add_api_route("/manifest", self._manifest)
        self.add_api_route("/screens/{name}", self._screen_payload)
        self.add_api_route("/actions/{name}", self._action_result, methods=["POST"])
        self.add_api_websocket_route("/ws/screens/{name}", self._screen_socket)

    def assets(self, directory: str) -> None:
        """Serve a directory of static files (tab icons, images) under /assets."""
        self.mount("/assets", StaticFiles(directory=directory), name="assets")

    def screen(self, name: str) -> Callable[[ScreenBuilder], ScreenBuilder]:
        def register(builder: ScreenBuilder) -> ScreenBuilder:
            self._screens[name] = builder
            return builder

        return register

    def action(self, name: str) -> Callable[[ActionHandler], ActionHandler]:
        """Register the handler that a Submit(name, ...) button posts to."""

        def register(handler: ActionHandler) -> ActionHandler:
            self._actions[name] = handler
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

    async def _manifest(self) -> dict[str, Any]:
        """App-level chrome the shells read once at startup: tabs and theme."""
        return {
            "tabs": [
                {"screen": tab.screen, "title": tab.title, "icon": tab.icon} for tab in self.tabs
            ],
            "theme": {"accent": self.theme.accent},
        }

    async def _screen_payload(self, name: str) -> dict[str, Any]:
        try:
            return self.render_screen(name)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"no screen named {name!r}") from None

    async def _action_result(self, name: str, values: dict[str, str]) -> dict[str, str | None]:
        handler = self._actions.get(name)
        if handler is None:
            raise HTTPException(status_code=404, detail=f"no action named {name!r}")
        result = handler(values)
        return {"navigate": result.screen if result else None}

    async def _screen_socket(self, websocket: WebSocket, name: str) -> None:
        """Send the screen once, then hold the socket open.

        Live reload rides on this: `uvicorn --reload` restarts the process on
        every code change, the socket drops, and the shell reconnects to get
        the fresh screen.
        """
        await websocket.accept()
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
