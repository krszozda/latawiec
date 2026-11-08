from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, TypedDict, cast

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from latawiec.components import Component, Navigate, render

# WebSocket close codes in the app-defined 4000-4999 range, echoing HTTP.
NO_SUCH_SCREEN = 4404
NOT_AUTHORIZED = 4401

_log = logging.getLogger("latawiec")


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
class AppLinks:
    """What /.well-known serves, so real https links open the app.

    `android_package` plus `android_fingerprints` (the SHA-256 of the
    signing certificate, e.g. `keytool -printcert -jarfile app.apk`; any
    case — it is normalized on the way out) feed assetlinks.json;
    `ios_app_id` is TEAMID.bundleid and feeds apple-app-site-association.
    Give only the side you ship and the other file stays 404.
    docs/shipping.md has the shell-side steps.
    """

    android_package: str | None = None
    android_fingerprints: tuple[str, ...] = ()
    ios_app_id: str | None = None

    def __post_init__(self) -> None:
        # An empty fingerprint list serves valid JSON that Android can
        # never verify — a silent install-time failure caught here instead.
        if self.android_package is not None and not self.android_fingerprints:
            raise ValueError("android_package needs at least one signing fingerprint")


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

    locale: str = ""
    """First Accept-Language tag the device sent, e.g. "pl-PL"; "" unknown."""

    platform: str = ""
    """"android" or "ios" from the shells; "" for any other client."""

    timezone: str = ""
    """The device's IANA zone id, e.g. "Europe/Warsaw"; "" unknown."""

    app_version: str = ""
    """The installed shell build's version name; "" unknown."""


# Builders, handlers, and the auth check may be sync or `async def`; sync
# ones run in a threadpool so a blocking call cannot stall the event loop.
ScreenBuilder = Callable[..., Component | Awaitable[Component]]
ActionResult = Navigate | Grant | None
ActionHandler = Callable[..., ActionResult | Awaitable[ActionResult]]
AuthHandler = Callable[[str | None], Any]
DeviceHandler = Callable[..., None | Awaitable[None]]


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


def _is_placeholder(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


@dataclass
class _Subscriber:
    """One phone holding a live screen open, with its request identity."""

    socket: WebSocket
    params: dict[str, str]
    authorization: str | None
    device: _Device


class _Device(TypedDict):
    locale: str
    platform: str
    timezone: str
    app_version: str


def _device(headers: Mapping[str, str]) -> _Device:
    """Context fields the shells report in headers on every request."""
    accept = headers.get("accept-language", "")
    first = accept.split(",")[0].split(";")[0].strip()
    return {
        # A browser's "anything goes" wildcard is not a locale.
        "locale": "" if first == "*" else first,
        "platform": headers.get("x-latawiec-platform", "").lower(),
        "timezone": headers.get("x-latawiec-timezone", ""),
        "app_version": headers.get("x-latawiec-app-version", ""),
    }


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
        app_links: AppLinks | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.app_links = app_links
        """Served under /.well-known so https links open the shells."""
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
        self._device_handler: tuple[DeviceHandler, bool] | None = None
        self._live: set[str] = set()
        self._refresh: dict[str, int] = {}
        self._subscribers: dict[str, list[_Subscriber]] = {}
        self._push_tasks: set[asyncio.Task[None]] = set()
        self._pushing: set[str] = set()
        self._dirty: set[str] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._screens: dict[str, tuple[ScreenBuilder, bool]] = {}
        self._actions: dict[str, tuple[ActionHandler, bool]] = {}
        self._public_screens: set[str] = set()
        self._public_actions: set[str] = set()
        self._cache: dict[str, CachePolicy] = {}
        self.add_api_route("/manifest", self._manifest)
        # :path, so screen names like "product/42" keep their slashes.
        self.add_api_route("/screens/{name:path}", self._screen_payload)
        self.add_api_route("/actions/{name}", self._action_result, methods=["POST"])
        self.add_api_route("/devices", self._register_device, methods=["POST"])
        self.add_api_route("/.well-known/assetlinks.json", self._assetlinks)
        self.add_api_route("/.well-known/apple-app-site-association", self._apple_association)
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

    def device(self, handler: DeviceHandler) -> DeviceHandler:
        """Register the push-token sink; registering it turns push on.

        The shells see "push": true in the manifest, ask for notification
        permission, and POST the platform's push token here — at startup and
        whenever the platform rotates it, so the handler must tolerate
        repeats. It gets the token and optionally a Context: ctx.platform
        tells FCM and APNs tokens apart, ctx.user is the signed-in user when
        a bearer token came along. Registration stays public by design —
        devices exist before anyone signs in — so decide in the handler what
        anonymous tokens are worth to you.

        Sending pushes stays on your side (your FCM/APNs credentials); put a
        screen path under the "screen" key of the message's data and the tap
        opens that screen like a deep link. See docs/shipping.md.
        """
        self._device_handler = (handler, _wants_context(handler, without=1))
        return handler

    def screen(
        self,
        name: str,
        *,
        public: bool = False,
        cache: CachePolicy | None = None,
        live: bool = False,
        refresh: int | None = None,
    ) -> Callable[[ScreenBuilder], ScreenBuilder]:
        """Register a screen; a {placeholder} as a whole path segment
        captures that segment as a param.

        The builder may take no arguments, or one `Context` with `ctx.user`
        and `ctx.params` — e.g. @app.screen("product/{id}") receives
        ctx.params["id"] when the shell navigates to "product/42". Exact
        names beat templates, a template with more literal segments beats a
        more general one, and a tie ("{a}/edit" next to "product/{id}")
        raises here rather than resolving by registration order.

        `cache` steers the shells' screen cache: "static" lives until the
        app version changes, "swr" (the default) renders from cache and
        revalidates, "no-store" never touches disk — which is also the
        default for guarded screens once auth is registered.

        `live=True` keeps the screen connected in production too: after the
        first render the shell subscribes over the socket, and every
        app.refresh(name) re-renders and pushes it — streaming is refreshing
        fast. `refresh=N` is the cheap alternative: the shell refetches the
        screen every N seconds while it is on display. One or the other.
        """
        if live and refresh is not None:
            raise ValueError("a screen is either live or polled, not both")
        if refresh is not None and refresh <= 0:
            raise ValueError("refresh is a positive number of seconds")

        def register(builder: ScreenBuilder) -> ScreenBuilder:
            clash = self._ambiguous_with(name)
            if clash is not None:
                raise ValueError(
                    f"screen {name!r} ties with {clash!r}: both can match the "
                    "same path at the same specificity, so the winner would "
                    "be registration order — rename a segment instead"
                )
            self._screens[name] = (builder, _wants_context(builder, without=0))
            if public:
                self._public_screens.add(name)
            if cache is not None:
                self._cache[name] = cache
            if live:
                self._live.add(name)
            if refresh is not None:
                self._refresh[name] = refresh
            return builder

        return register

    def refresh(self, name: str) -> None:
        """Re-render a live screen for every phone showing it, now.

        Each subscriber gets its own render (its user, params, and device
        context), with its access re-checked — a revoked token closes the
        subscription. Callable from sync and async handlers alike; before
        the server starts serving there is nobody to refresh, so it is a
        no-op. Bursts coalesce: pushes of one screen run one at a time, and
        refreshes landing mid-push fold into a single trailing re-render.
        """
        if name not in self._screens:
            raise KeyError(f"no screen named {name!r}")
        loop = self._loop
        if loop is None:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            task = loop.create_task(self._push(name))
            # An unreferenced task may be collected mid-flight.
            self._push_tasks.add(task)
            task.add_done_callback(self._push_tasks.discard)
        else:
            asyncio.run_coroutine_threadsafe(self._push(name), loop)

    async def _push(self, name: str) -> None:
        if name in self._pushing:
            self._dirty.add(name)
            return
        self._pushing.add(name)
        try:
            while True:
                self._dirty.discard(name)
                for subscriber in list(self._subscribers.get(name, ())):
                    await self._push_one(name, subscriber)
                if name not in self._dirty:
                    return
        finally:
            self._pushing.discard(name)
            self._dirty.discard(name)

    async def _push_one(self, name: str, subscriber: _Subscriber) -> None:
        # Re-checked per push: a token revoked mid-subscription must not
        # keep receiving guarded renders.
        allowed, user = await self._access(name, self._public_screens, subscriber.authorization)
        try:
            if not allowed:
                await subscriber.socket.close(code=NOT_AUTHORIZED, reason="not authorized")
                return
            payload = await self._render(name, subscriber.params, user, subscriber.device)
            await subscriber.socket.send_json(payload)
        except (WebSocketDisconnect, RuntimeError):
            # A socket that died mid-send; its handler unregisters it.
            return
        except Exception:
            # One subscriber's broken render must not starve the rest.
            _log.exception("pushing %r to a subscriber failed", name)

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
        """Render a screen by path (no user, no device context) to the
        payload a shell renders.

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
        """Match a requested path to a registered name.

        Exact names win; among matching templates the one with the fewest
        placeholders (most literal segments) wins. The equal-specificity
        case cannot arise: screen() rejects it at registration.
        """
        if name in self._screens:
            return name, {}
        parts = name.split("/")
        best: tuple[int, str, dict[str, str]] | None = None
        for template in self._screens:
            if "{" not in template:
                continue
            segments = template.split("/")
            if len(segments) != len(parts):
                continue
            params: dict[str, str] = {}
            for segment, part in zip(segments, parts, strict=True):
                if _is_placeholder(segment):
                    params[segment[1:-1]] = part
                elif segment != part:
                    break
            else:
                holes = sum(map(_is_placeholder, segments))
                if best is None or holes < best[0]:
                    best = (holes, template, params)
        if best is None:
            return None
        return best[1], best[2]

    def _ambiguous_with(self, name: str) -> str | None:
        """An already-registered template this one ties with.

        Two templates tie when they can match the same path with the same
        number of placeholders — "{a}/edit" and "product/{id}" both claim
        "product/edit" and neither is more specific, so the choice would be
        registration order: silent and surprising. Caught here instead.
        """
        if "{" not in name:
            return None
        segments = name.split("/")
        holes = sum(map(_is_placeholder, segments))
        for other in self._screens:
            # Re-registering a name overwrites it, as it always did.
            if other == name or "{" not in other:
                continue
            others = other.split("/")
            if len(others) != len(segments):
                continue
            if sum(map(_is_placeholder, others)) != holes:
                continue
            overlapping = all(
                a == b or _is_placeholder(a) or _is_placeholder(b)
                for a, b in zip(segments, others, strict=True)
            )
            if overlapping:
                return other
        return None

    async def _render(
        self, template: str, params: dict[str, str], user: Any, device: _Device
    ) -> dict[str, Any]:
        builder, wants_context = self._screens[template]
        args = (Context(user=user, params=params, **device),) if wants_context else ()
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
            "push": self._device_handler is not None,
        }

    async def _screen_payload(
        self,
        name: str,
        request: Request,
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
        headers = {
            "Cache-Control": _CACHE_HEADERS[self._cache_policy(template)],
            # Renders may depend on the device context, so a shared HTTP
            # cache must key on these headers too.
            "Vary": (
                "Accept-Language, X-Latawiec-Platform, X-Latawiec-Timezone, X-Latawiec-App-Version"
            ),
        }
        # After this render the shell subscribes (live) or refetches (poll).
        if template in self._live:
            headers["X-Latawiec-Live"] = "1"
        elif template in self._refresh:
            headers["X-Latawiec-Refresh"] = str(self._refresh[template])
        return JSONResponse(
            content=await self._render(template, resolved[1], user, _device(request.headers)),
            headers=headers,
        )

    async def _action_result(
        self,
        name: str,
        values: dict[str, str],
        request: Request,
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
        args = (
            (values, Context(user=user, **_device(request.headers))) if wants_context else (values,)
        )
        result = await _call(handler, *args)
        if isinstance(result, Grant):
            return {"navigate": result.screen, "token": result.token}
        return {"navigate": result.screen if result else None}

    async def _assetlinks(self) -> JSONResponse:
        """Android's domain-ownership proof for App Links."""
        links = self.app_links
        if links is None or links.android_package is None:
            raise HTTPException(status_code=404, detail="no Android app links declared")
        return JSONResponse(
            [
                {
                    "relation": ["delegate_permission/common.handle_all_urls"],
                    "target": {
                        "namespace": "android_app",
                        "package_name": links.android_package,
                        # The verifier compares uppercase colon-separated hex.
                        "sha256_cert_fingerprints": [
                            fingerprint.upper() for fingerprint in links.android_fingerprints
                        ],
                    },
                }
            ]
        )

    async def _apple_association(self) -> JSONResponse:
        """iOS's domain-ownership proof for Universal Links."""
        links = self.app_links
        if links is None or links.ios_app_id is None:
            raise HTTPException(status_code=404, detail="no iOS app links declared")
        return JSONResponse(
            {"applinks": {"details": [{"appIDs": [links.ios_app_id], "components": [{"/": "/*"}]}]}}
        )

    async def _register_device(
        self,
        body: dict[str, str],
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, bool]:
        if self._device_handler is None:
            raise HTTPException(status_code=404, detail="the app registered no device handler")
        token = body.get("token", "")
        if not token:
            raise HTTPException(status_code=422, detail="token required")
        # Public on purpose (see device()), but the user still rides along
        # when a valid bearer token came with the request.
        user = None
        if self._auth is not None:
            user = await _call(self._auth, _bearer(authorization)) or None
        handler, wants_context = self._device_handler
        args = (
            (token, Context(user=user, **_device(request.headers))) if wants_context else (token,)
        )
        await _call(handler, *args)
        return {"registered": True}

    async def _screen_socket(self, websocket: WebSocket, name: str) -> None:
        """Send the screen once, then hold the socket open.

        Live reload rides on this: `uvicorn --reload` restarts the process on
        every code change, the socket drops, and the shell reconnects to get
        the fresh screen.
        """
        await websocket.accept()
        # refresh() schedules onto this loop, also from threadpooled
        # handlers; without a subscriber it has nothing to do anyway.
        self._loop = asyncio.get_running_loop()
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
        device = _device(websocket.headers)
        await websocket.send_json(await self._render(resolved[0], resolved[1], user, device))
        # From here the socket doubles as the live subscription: every
        # app.refresh(name) re-renders and pushes to it.
        subscriber = _Subscriber(
            websocket, resolved[1], websocket.headers.get("authorization"), device
        )
        waiting = self._subscribers.setdefault(resolved[0], [])
        waiting.append(subscriber)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            waiting.remove(subscriber)
