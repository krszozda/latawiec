from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException

from latawiec.components import Component, render

ScreenBuilder = Callable[[], Component]


class Latawiec(FastAPI):
    """An ASGI app that serves Latawiec screens; run it like any FastAPI app."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._screens: dict[str, ScreenBuilder] = {}
        self.add_api_route("/screens/{name}", self._screen_payload)

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
