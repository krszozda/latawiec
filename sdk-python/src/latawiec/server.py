from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from latawiec.components import Component, render

ScreenBuilder = Callable[[], Component]

# WebSocket close code in the app-defined 4000-4999 range, echoing HTTP 404.
NO_SUCH_SCREEN = 4404


class Latawiec(FastAPI):
    """An ASGI app that serves Latawiec screens; run it like any FastAPI app."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._screens: dict[str, ScreenBuilder] = {}
        self.add_api_route("/screens/{name}", self._screen_payload)
        self.add_api_websocket_route("/ws/screens/{name}", self._screen_socket)

    def screen(self, name: str) -> Callable[[ScreenBuilder], ScreenBuilder]:
        def register(builder: ScreenBuilder) -> ScreenBuilder:
            self._screens[name] = builder
            return builder

        return register

    async def _screen_payload(self, name: str) -> dict[str, Any]:
        builder = self._screens.get(name)
        if builder is None:
            raise HTTPException(status_code=404, detail=f"no screen named {name!r}")
        return render(builder())

    async def _screen_socket(self, websocket: WebSocket, name: str) -> None:
        """Send the screen once, then hold the socket open.

        Live reload rides on this: `uvicorn --reload` restarts the process on
        every code change, the socket drops, and the shell reconnects to get
        the fresh screen.
        """
        await websocket.accept()
        builder = self._screens.get(name)
        if builder is None:
            await websocket.close(code=NO_SUCH_SCREEN, reason=f"no screen named {name!r}")
            return
        await websocket.send_json(render(builder()))
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
