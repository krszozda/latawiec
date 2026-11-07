from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, cast

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from latawiec.components import Component, Navigate, render

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


@dataclass(frozen=True)
class Context:
    """What a request carries into a screen builder or action handler."""

    user: Any = None
    """Whatever @app.auth returned for this request's token; None when the
    app has no auth or no valid token came along."""

    params: dict[str, str] = field(default_factory=dict[str, str])
    """Values captured by {placeholders} in the screen's registered name."""


# Builders, handlers, and the auth check may be sync or `async def`; sync
# ones run in a threadpool so a blocking call cannot stall the event loop.
ScreenBuilder = Callable[..., Component | Awaitable[Component]]
ActionResult = Navigate | Grant | None
ActionHandler = Callable[..., ActionResult | Awaitable[ActionResult]]
AuthHandler = Callable[[str | None], Any]


async def _call(handler: Callable[..., Any], *args: Any) -> Any:
    if inspect.iscoroutinefunction(handler):
        return await handler(*args)
    return await run_in_threadpool(handler, *args)


def _bearer(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    return token if scheme.lower() == "bearer" and token else None


def _wants_context(handler: Callable[..., Any], without: int) -> bool:
    return len(inspect.signature(handler).parameters) > without


CachePolicy = Literal["static", "swr", "no-store"]

# What each policy tells a shell's (or any HTTP) cache on GET /screens.
_CACHE_HEADERS: dict[CachePolicy, str] = {
    "static": "max-age=31536000, immutable",
    "swr": "max-age=0, stale-while-revalidate=86400",
    "no-store": "no-store",
}


class Latawiec(FastAPI):
    """An ASGI app that serves Latawiec screens; run it like any FastAPI app."""

    def __init__(
        self,
        *,
        tabs: Sequence[Tab] = (),
        theme: Theme | None = None,
        login: str | None = None,
        version: str | None = None,
        dev: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.tabs = tuple(tabs)
        self.theme = theme or Theme()
        self.login = login
        """Screen the shells show when the server answers 401/4401."""
        self.version = version
        """Content version; a change tells the shells to drop cached screens."""
        self.dev = dev
        """Dev keeps the live-reload sockets; deploy with dev=False so shells
        fetch screens over GET and cache them per policy."""
        self._auth: AuthHandler | None = None
        self._screens: dict[str, tuple[ScreenBuilder, bool]] = {}
        self._actions: dict[str, tuple[ActionHandler, bool]] = {}
        self._public_screens: set[str] = set()
        self._public_actions: set[str] = set()
        self._cache: dict[str, CachePolicy] = {}
        self.add_api_route("/manifest", self._manifest)
        # :path, so screen names like "product/42" keep their slashes.
        self.add_api_route("/screens/{name:path}", self._screen_payload)
        self.add_api_route("/actions/{name}", self._action_result, methods=["POST"])
        self.add_api_websocket_route("/ws/screens/{name:path}", self._screen_socket)

    def assets(self, directory: str) -> None:
        """Serve a directory of static files (tab icons, images) under /assets."""
        self.mount("/assets", StaticFiles(directory=directory), name="assets")

    def auth(self, handler: AuthHandler) -> AuthHandler:
        """Register the token check; it gets the bearer token (or None) and
        returns a truthy user object, or None/False to reject.

        Once registered, screens and actions answer 401 (sockets close with
        4401) unless the handler accepts the token or they were registered
        with public=True. The manifest and /assets stay public: the shell
        needs them to show the login screen in the first place. Whatever the
        handler returns arrives in builders and handlers as `ctx.user`.
        """
        self._auth = handler
        return handler

    def screen(
        self,
        name: str,
        *,
        public: bool = False,
        cache: CachePolicy | None = None,
    ) -> Callable[[ScreenBuilder], ScreenBuilder]:
        """Register a screen; a {placeholder} as a whole path segment
        captures that segment as a param.

        The builder may take no arguments, or one `Context` with `ctx.user`
        and `ctx.params` — e.g. @app.screen("product/{id}") receives
        ctx.params["id"] when the shell navigates to "product/42".

        `cache` steers the shells' screen cache: "static" lives until the
        app version changes, "swr" (the default) renders from cache and
        revalidates, "no-store" never touches disk — which is also the
        default for guarded screens once auth is registered.
        """

        def register(builder: ScreenBuilder) -> ScreenBuilder:
            self._screens[name] = (builder, _wants_context(builder, without=0))
            if public:
                self._public_screens.add(name)
            if cache is not None:
                self._cache[name] = cache
            return builder

        return register

    def action(
        self, name: str, *, public: bool = False
    ) -> Callable[[ActionHandler], ActionHandler]:
        """Register the handler that a Submit(name, ...) button posts to.

        The handler takes the submitted values, and optionally a `Context`
        as its second argument.
        """

        def register(handler: ActionHandler) -> ActionHandler:
            self._actions[name] = (handler, _wants_context(handler, without=1))
            if public:
                self._public_actions.add(name)
            return handler

        return register

    @property
    def screen_names(self) -> tuple[str, ...]:
        return tuple(self._screens)

    def render_screen(self, name: str) -> dict[str, Any]:
        """Render a screen by path (no user) to the payload a shell renders.

        Synchronous for callers like the MCP tools; an `async def` builder
        is driven with asyncio.run, so call it outside an event loop.
        """
        resolved = self._resolve(name)
        if resolved is None:
            raise KeyError(f"no screen named {name!r}")
        template, params = resolved
        builder, wants_context = self._screens[template]
        args = (Context(params=params),) if wants_context else ()
        component = builder(*args)
        if not isinstance(component, Component):
            component = asyncio.run(cast("Coroutine[Any, Any, Component]", component))
        return render(component)

    def _cache_policy(self, template: str) -> CachePolicy:
        explicit = self._cache.get(template)
        if explicit is not None:
            return explicit
        # Guarded content stays off disk unless the app opts in.
        if self._auth is not None and template not in self._public_screens:
            return "no-store"
        return "swr"

    def _resolve(self, name: str) -> tuple[str, dict[str, str]] | None:
        """Match a requested path to a registered name; exact names win."""
        if name in self._screens:
            return name, {}
        parts = name.split("/")
        for template in self._screens:
            if "{" not in template:
                continue
            segments = template.split("/")
            if len(segments) != len(parts):
                continue
            params: dict[str, str] = {}
            for segment, part in zip(segments, parts, strict=True):
                if segment.startswith("{") and segment.endswith("}"):
                    params[segment[1:-1]] = part
                elif segment != part:
                    break
            else:
                return template, params
        return None

    async def _render(self, template: str, params: dict[str, str], user: Any) -> dict[str, Any]:
        builder, wants_context = self._screens[template]
        args = (Context(user=user, params=params),) if wants_context else ()
        return render(await _call(builder, *args))

    async def _access(
        self, template: str | None, public: set[str], authorization: str | None
    ) -> tuple[bool, Any]:
        """Whether the request may proceed, and who it is.

        Auth is checked before existence (template None means unresolved), so
        anonymous requests cannot probe which screens exist. Public surfaces
        still learn the user when a valid token comes along.
        """
        if self._auth is None:
            return True, None
        # Falsy means rejected — so a legacy handler returning False cannot
        # accidentally open every guarded screen.
        user = await _call(self._auth, _bearer(authorization)) or None
        if template in public:
            return True, user
        return user is not None, user

    async def _manifest(self) -> dict[str, Any]:
        """App-level chrome the shells read once at startup: tabs, theme, login."""
        return {
            "tabs": [
                {"screen": tab.screen, "title": tab.title, "icon": tab.icon} for tab in self.tabs
            ],
            "theme": {"accent": self.theme.accent},
            "login": self.login,
            "version": self.version,
            "dev": self.dev,
        }

    async def _screen_payload(
        self,
        name: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        resolved = self._resolve(name)
        template = resolved[0] if resolved else None
        allowed, user = await self._access(template, self._public_screens, authorization)
        if not allowed:
            raise HTTPException(
                status_code=401,
                detail="not authorized",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if resolved is None:
            raise HTTPException(status_code=404, detail=f"no screen named {name!r}")
        template = resolved[0]
        return JSONResponse(
            content=await self._render(template, resolved[1], user),
            headers={"Cache-Control": _CACHE_HEADERS[self._cache_policy(template)]},
        )

    async def _action_result(
        self,
        name: str,
        values: dict[str, str],
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, str | None]:
        registered = self._actions.get(name)
        allowed, user = await self._access(
            name if registered else None, self._public_actions, authorization
        )
        if not allowed:
            raise HTTPException(
                status_code=401,
                detail="not authorized",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if registered is None:
            raise HTTPException(status_code=404, detail=f"no action named {name!r}")
        handler, wants_context = registered
        args = (values, Context(user=user)) if wants_context else (values,)
        result = await _call(handler, *args)
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
        resolved = self._resolve(name)
        template = resolved[0] if resolved else None
        allowed, user = await self._access(
            template, self._public_screens, websocket.headers.get("authorization")
        )
        if not allowed:
            await websocket.close(code=NOT_AUTHORIZED, reason="not authorized")
            return
        if resolved is None:
            await websocket.close(code=NO_SUCH_SCREEN, reason=f"no screen named {name!r}")
            return
        await websocket.send_json(await self._render(resolved[0], resolved[1], user))
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
