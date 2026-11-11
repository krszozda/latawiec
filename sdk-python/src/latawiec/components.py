from __future__ import annotations

import mimetypes
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Literal
from urllib.parse import quote

import pydivkit as dv
from pydivkit.core import Expr

Size = int | Literal["fill", "wrap"]
HorizontalAlign = Literal["left", "center", "right"]
VerticalAlign = Literal["top", "center", "bottom"]
FontWeight = Literal["light", "regular", "medium", "bold"]


@dataclass(frozen=True)
class Edges:
    """Per-side spacing, for when a single number is not enough."""

    top: int = 0
    right: int = 0
    bottom: int = 0
    left: int = 0


def _insets(spec: int | Edges) -> dv.DivEdgeInsets:
    if isinstance(spec, int):
        spec = Edges(top=spec, right=spec, bottom=spec, left=spec)
    return dv.DivEdgeInsets(top=spec.top, right=spec.right, bottom=spec.bottom, left=spec.left)


def _size(spec: Size) -> dv.DivSize:
    if isinstance(spec, int):
        return dv.DivFixedSize(value=spec)
    return dv.DivMatchParentSize() if spec == "fill" else dv.DivWrapContentSize()


@dataclass(frozen=True)
class Fade:
    """Appearance transition: the component fades in (or out)."""

    duration: int = 300
    delay: int = 0


@dataclass(frozen=True)
class Slide:
    """Appearance transition: slides in from (or out through) an edge."""

    edge: Literal["left", "top", "right", "bottom"] = "bottom"
    duration: int = 300
    delay: int = 0


@dataclass(frozen=True)
class Grow:
    """Appearance transition: scales up from nothing (or shrinks away)."""

    duration: int = 300
    delay: int = 0


Transition = Fade | Slide | Grow


def _appearance(
    transition: Transition,
) -> dv.DivFadeTransition | dv.DivSlideTransition | dv.DivScaleTransition:
    if isinstance(transition, Fade):
        return dv.DivFadeTransition(
            duration=transition.duration, start_delay=transition.delay or None
        )
    if isinstance(transition, Slide):
        return dv.DivSlideTransition(
            edge=dv.DivSlideTransitionEdge(transition.edge),
            duration=transition.duration,
            start_delay=transition.delay or None,
        )
    return dv.DivScaleTransition(duration=transition.duration, start_delay=transition.delay or None)


# Appearance transitions also fire on live refreshes (data_change), so a
# streamed chat bubble fades in instead of popping.
_TRANSITION_TRIGGERS = [
    dv.DivTransitionTrigger.DATA_CHANGE,
    dv.DivTransitionTrigger.STATE_CHANGE,
    dv.DivTransitionTrigger.VISIBILITY_CHANGE,
]


@dataclass(frozen=True)
class Style:
    """Visual options every component accepts; unset fields keep the component's own look.

    Sizes and spacing are in density-independent pixels; "fill" and "wrap"
    match the parent and the content. `align` places the component inside
    its parent (it does not align text — Text has its own `align`), and has
    a visible effect only with width="wrap" or a fixed width: DivKit sizes
    elements to the parent's width by default.
    """

    padding: int | Edges | None = None
    margin: int | Edges | None = None
    width: Size | None = None
    height: Size | None = None
    background: str | None = None
    corner_radius: int | None = None
    border: str | None = None
    align: HorizontalAlign | None = None
    align_vertical: VerticalAlign | None = None
    alpha: float | None = None
    appear: Transition | None = None
    """How the component enters: Fade(), Slide("bottom"), or Grow()."""
    disappear: Transition | None = None
    """How it leaves; a vanished component animates out instead of popping."""
    move: int | None = None
    """Layout changes animate over this many milliseconds."""

    def apply(self, div: dv.Div) -> dv.Div:
        if self.padding is not None:
            div.paddings = _insets(self.padding)
        if self.margin is not None:
            div.margins = _insets(self.margin)
        if self.width is not None:
            div.width = _size(self.width)
        if self.height is not None:
            div.height = _size(self.height)
        if self.background is not None:
            div.background = [dv.DivSolidBackground(color=self.background)]
        if self.corner_radius is not None or self.border is not None:
            # Merge with the border the component built (e.g. Button's radius,
            # TextInput's stroke), so setting one half keeps the other.
            current = div.border
            div.border = dv.DivBorder(
                corner_radius=(
                    self.corner_radius
                    if self.corner_radius is not None
                    else (current.corner_radius if current else None)
                ),
                stroke=(
                    dv.DivStroke(color=self.border)
                    if self.border
                    else (current.stroke if current else None)
                ),
            )
        if self.align is not None:
            div.alignment_horizontal = dv.DivAlignmentHorizontal(self.align)
        if self.align_vertical is not None:
            div.alignment_vertical = dv.DivAlignmentVertical(self.align_vertical)
        if self.alpha is not None:
            div.alpha = self.alpha
        if self.appear is not None:
            div.transition_in = _appearance(self.appear)
        if self.disappear is not None:
            div.transition_out = _appearance(self.disappear)
        if self.move is not None:
            div.transition_change = dv.DivChangeBoundsTransition(duration=self.move)
        if self.appear is not None or self.disappear is not None or self.move is not None:
            div.transition_triggers = _TRANSITION_TRIGGERS
        return div


class Expression(str):
    """A string the shells evaluate instead of showing as written.

    Every other string reaching a component is shown exactly as typed,
    "@{...}" included, because most of them carry someone's name, a
    review, a product title — content, which must never be read as code.
    Wrap one in this to opt into DivKit's expressions:

        Text(Expression("Hello, @{name}!"))

    Whatever goes inside is yours to vouch for: a value that arrived from
    outside your app does not belong in one.

    It is a str, and only the str itself is marked: slicing it, adding to
    it or putting it in an f-string gives back a plain string, which is
    shown as written like any other.
    """


# Two characters cannot travel as themselves in a string DivKit reads:
# "@{" opens an expression, and a backslash escapes inside one, so a lone
# backslash makes Android render the whole text as nothing and makes iOS
# drop the run it sits in. Each is therefore sent as its own small
# expression that evaluates to it.
#
# Escaping them in place instead — "\\@{", "\\\\" — is what both platforms
# document, and it does not hold up:
#
# - Android's tokenizer reads "a \\@{b}" as a plain literal with no
#   template in it, while the field is still routed through the evaluator
#   because the raw string holds "@{"; the text renders as nothing.
# - A backslash in front of either form escapes it, so the escape itself
#   ends up on screen.
#
# Inside the expressions below they are quoted, where escaping them does
# work. LiteralEscapingTest in shell-android puts these spellings through
# DivKit's own evaluator — the one place a test can reach it — and the
# tests here pin what this function produces, so changing either side
# means changing both.
_SHOW_MARKER = "@{'\\@{'}"
_SHOW_BACKSLASH = "@{'\\\\'}"
_DANGEROUS = re.compile(r"\\|@\{")


def _literal(text: str) -> str:
    """The string as DivKit has to be given it to show it unchanged.

    An Expression is handed over as it is: it asked to be evaluated.
    """
    if isinstance(text, Expression):
        return text
    return _DANGEROUS.sub(
        lambda hit: _SHOW_BACKSLASH if hit.group() == "\\" else _SHOW_MARKER, text
    )


class Component(ABC):
    """A node of the UI tree."""

    style: Style | None = None

    @abstractmethod
    def _build(self) -> dv.Div: ...

    def to_div(self) -> dv.Div:
        div = self._build()
        return self.style.apply(div) if self.style else div


@dataclass(frozen=True)
class Text(Component):
    text: str
    size: int | None = None
    color: str | None = None
    weight: FontWeight | None = None
    align: HorizontalAlign | None = None
    line_height: int | None = None
    style: Style | None = None

    def _build(self) -> dv.Div:
        return dv.DivText(
            text=_literal(self.text),
            font_size=self.size,
            text_color=self.color,
            font_weight=dv.DivFontWeight(self.weight) if self.weight else None,
            text_alignment_horizontal=(
                dv.DivAlignmentHorizontal(self.align) if self.align else None
            ),
            line_height=self.line_height,
        )


@dataclass(frozen=True)
class Image(Component):
    """A picture, fetched by the platform's own image loader.

    The URL has to be absolute: it goes to that loader untouched, so a
    path relative to your server means nothing to it. A tab icon is the
    exception — the shell fetches those itself.
    """

    url: str
    style: Style | None = None

    def _build(self) -> dv.Div:
        return dv.DivImage(image_url=_literal(self.url))


@dataclass(frozen=True)
class Navigate:
    """Tap action: ask the shell to fetch and show another screen."""

    screen: str

    def to_div_action(self) -> dv.DivAction:
        return dv.DivAction(
            log_id=f"navigate:{_literal(self.screen)}",
            url=f"latawiec://navigate?screen={quote(self.screen, safe='')}",
        )


@dataclass(frozen=True)
class SetVariable:
    """Tap action: assign a string to a screen variable, on the device.

    The variable does not have to belong to a control: naming one here is
    enough for the screen to declare it, so `Text(Expression("@{mood}"))`
    beside the button reads what the tap wrote.
    """

    variable: str
    value: str

    def to_div_action(self) -> dv.DivAction:
        return dv.DivAction(
            log_id=f"set:{_literal(self.variable)}",
            typed=dv.DivActionSetVariable(
                variable_name=_literal(self.variable),
                value=dv.StringValue(value=_literal(self.value)),
            ),
        )


def _reject_reserved(send: tuple[str, ...], reserved: tuple[str, ...]) -> None:
    """A variable sharing a name with the URL's own keys would be dropped."""
    clash = [name for name in send if name in reserved]
    if clash:
        raise ValueError(f"cannot send {clash[0]!r}: the action URL already uses that name")


@dataclass(frozen=True)
class Submit:
    """Tap action: POST the named screen variables to a server action handler.

    Variable values travel inside the action URL as @{encodeUri(...)}
    expressions, which DivKit evaluates at tap time — the shell only parses
    query parameters and never reads variables itself.
    """

    action: str
    send: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _reject_reserved(self.send, ("action",))

    def to_div_action(self) -> dv.DivAction:
        query = "".join(f"&{name}=@{{encodeUri({name})}}" for name in self.send)
        return dv.DivAction(
            log_id=f"submit:{_literal(self.action)}",
            url=f"latawiec://submit?action={quote(self.action, safe='')}{query}",
        )


@dataclass(frozen=True)
class Unlock:
    """Tap action: ask for the device unlock, then submit `action`.

    Face ID, a fingerprint, or the device passcode — whichever the phone
    offers. The submitted values travel exactly as Submit's do, and the
    handler may answer with a Navigate.

    This is a gate in front of a tap, not proof for your server: the shell
    submits the action once the check passes, and nothing stops a patched
    client from submitting it anyway. Anything that must not happen for
    the wrong person still needs @app.auth and a check in the handler.

    A device with nothing enrolled, and a user who cancels, submit
    nothing; the first case says why.
    """

    action: str
    send: tuple[str, ...] = ()
    reason: str = "Confirm it's you"
    """Shown in the system prompt, so say what is being confirmed."""

    def __post_init__(self) -> None:
        # Both shells raise their prompt with this as its title, and both
        # platforms reject an empty one — iOS by throwing.
        if not self.reason:
            raise ValueError("Unlock needs a reason: it is the prompt's title")
        _reject_reserved(self.send, ("action", "reason"))

    def to_div_action(self) -> dv.DivAction:
        query = "".join(f"&{name}=@{{encodeUri({name})}}" for name in self.send)
        return dv.DivAction(
            log_id=f"unlock:{_literal(self.action)}",
            url=(
                f"latawiec://unlock?action={quote(self.action, safe='')}"
                f"&reason={quote(self.reason, safe='')}{query}"
            ),
        )


@dataclass(frozen=True)
class SignOut:
    """Tap action: drop the token AND every cached screen, then start over.

    Both go together on purpose — on a shared phone the next user must not
    see the previous one's cached renders. The shell lands on `screen`,
    falling back to the manifest's login screen, then "home".
    """

    screen: str | None = None

    def to_div_action(self) -> dv.DivAction:
        query = f"?screen={quote(self.screen, safe='')}" if self.screen else ""
        return dv.DivAction(log_id="signout", url=f"latawiec://signout{query}")


@dataclass(frozen=True)
class RequestLocation:
    """Tap action: ask the device where it is, into `variable` as "lat,lon".

    The first tap raises the system permission prompt, so this belongs on a
    control the user pressed on purpose. A denial, or a fix that never
    arrives, leaves the variable empty and the screen decides what that
    means. `then` submits an action once the answer is in — pairing the two
    in a tuple instead would fire the submit before the fix arrives.
    """

    variable: str
    then: str | None = None

    def to_div_action(self) -> dv.DivAction:
        then = f"&action={quote(self.then, safe='')}" if self.then else ""
        return dv.DivAction(
            log_id="locate",
            url=f"latawiec://locate?variable={quote(self.variable, safe='')}{then}",
        )


@dataclass(frozen=True)
class Purchase:
    """Tap action: buy through the store, then submit `action` with the receipt.

    The shell runs the platform's own flow — StoreKit, Google Play Billing
    — and submits `action` with the receipt under "receipt", plus
    "signature" on Android. Nothing else: the product id is deliberately
    absent, because in the request it would be the client's word.

    Your handler has to do three things before granting anything:

    1. verify the receipt with Apple or Google;
    2. read the product id out of the verified receipt, never out of the
       request;
    3. remember the transaction id (Apple) or order id (Google) and refuse
       one it has already granted, since the same receipt can be POSTed
       again.

    The shell is a buy button, not proof of payment. Until the handler
    answers 200 the purchase stays unsettled on purpose, so a lost
    connection means the store redelivers it rather than the customer
    paying for nothing; set `consumable` for something that can be bought
    again, like a pack of coins, and the shell consumes it once the handler
    grants.

    A cancelled purchase submits nothing. A product the store does not know
    says so, as does a store it cannot reach.
    """

    product: str
    action: str
    consumable: bool = False

    def to_div_action(self) -> dv.DivAction:
        return dv.DivAction(
            log_id=f"buy:{_literal(self.product)}",
            url=(
                f"latawiec://buy?product={quote(self.product, safe='')}"
                f"&action={quote(self.action, safe='')}"
                f"{'&consumable=1' if self.consumable else ''}"
            ),
        )


@dataclass(frozen=True)
class Share:
    """Tap action: open the system share sheet with the text."""

    text: str

    def to_div_action(self) -> dv.DivAction:
        return dv.DivAction(
            log_id="share",
            url=f"latawiec://share?text={quote(self.text, safe='')}",
        )


@dataclass(frozen=True)
class OpenUrl:
    """Tap action: leave the app for the URL — browser, mail, or dialer.

    The shells only follow http(s), mailto, tel, and sms links.
    """

    url: str

    def to_div_action(self) -> dv.DivAction:
        # Unlike a screen name, the target may be a tel/mailto URL — personal
        # data that does not belong in an analytics log_id.
        return dv.DivAction(
            log_id="open",
            url=f"latawiec://open?url={quote(self.url, safe='')}",
        )


@dataclass(frozen=True)
class CopyToClipboard:
    """Tap action: put the text on the clipboard (DivKit handles it natively)."""

    text: str

    def to_div_action(self) -> dv.DivAction:
        return dv.DivAction(
            log_id="copy",
            typed=dv.DivActionCopyToClipboard(content=dv.ContentText(value=_literal(self.text))),
        )


@dataclass(frozen=True)
class Haptic:
    """Tap action: haptic feedback (DivKit handles it natively).

    Pair it with another action: on_tap=(Haptic("success"), Submit(...)).
    """

    feedback: Literal["light", "medium", "heavy", "success", "error"] = "light"

    def to_div_action(self) -> dv.DivAction:
        return dv.DivAction(
            log_id=f"haptic:{self.feedback}",
            typed=dv.DivActionHaptic(feedback=dv.DivActionHapticFeedback(self.feedback)),
        )


Action = (
    Navigate
    | SetVariable
    | Submit
    | Share
    | OpenUrl
    | CopyToClipboard
    | Haptic
    | SignOut
    | RequestLocation
    | Unlock
    | Purchase
)


@dataclass(frozen=True)
class LoadMore(Component):
    """The infinite-scroll sentinel: put it last in a Gallery.

    When it scrolls into view it submits `action` (no variables); the
    handler extends what the screen renders and calls app.refresh(), so
    pair it with live=True. Render it only while there is more — a
    sentinel left in an exhausted list re-fires on every refresh — and
    make the handler tolerate a duplicate fire (scrolling the sentinel
    out and back in before the refresh lands sends the action again).

    It fires on becoming visible, so each page must be long enough to push
    it back off the screen: a page that still fits on a tablet after
    loading leaves the sentinel in view, and nothing more arrives.
    """

    action: str
    label: str = "Loading more…"
    style: Style | None = None

    def _build(self) -> dv.Div:
        return dv.DivText(
            text=_literal(self.label),
            text_alignment_horizontal=dv.DivAlignmentHorizontal.CENTER,
            paddings=dv.DivEdgeInsets(top=16, bottom=16),
            visibility_actions=[
                dv.DivVisibilityAction(
                    log_id=f"more:{_literal(self.action)}",
                    url=f"latawiec://submit?action={quote(self.action, safe='')}",
                    # Unlimited: Android keys fire-counters by (card, log_id)
                    # and never resets them across refreshes, so the default
                    # limit of 1 would end the scroll after a single page.
                    log_limit=0,
                    # Fire fast: the default wants 800 ms of continuous
                    # visibility, which a fling never grants the sentinel.
                    visibility_duration=100,
                    visibility_percentage=1,
                )
            ],
        )


_PICKER_LABELS = {"gallery": "Choose a photo", "camera": "Take a photo"}


@dataclass(frozen=True)
class ImagePicker(Component):
    """A photo, uploaded the moment it is taken or picked.

    Tapping opens the system photo picker, or the camera with
    source="camera"; the shell uploads the result to the app's @app.upload
    handler and sets `variable` to whatever it returned — typically a URL,
    which this component then previews and a Submit(send=(variable,))
    forwards like any other variable.

    The camera needs no permission of its own on Android (the system camera
    app takes the photo). A device with no camera, or one whose owner turned
    camera access off, says so instead of silently falling back to the
    gallery.
    """

    variable: str
    label: str | None = None
    """Defaults to what the source offers: picking a photo, or taking one."""
    height: int = 160
    style: Style | None = None
    # Last on purpose: inserting it earlier would reinterpret the positional
    # arguments of apps written against an earlier release.
    source: Literal["gallery", "camera"] = "gallery"

    def _build(self) -> dv.Div:
        return dv.DivContainer(
            items=[
                dv.DivText(
                    text=_PICKER_LABELS[self.source]
                    if self.label is None
                    else _literal(self.label),
                    visibility=Expr(f"@{{{self.variable} == '' ? 'visible' : 'gone'}}"),
                    text_alignment_horizontal=dv.DivAlignmentHorizontal.CENTER,
                ),
                dv.DivImage(
                    image_url=f"@{{{self.variable}}}",
                    visibility=Expr(f"@{{{self.variable} != '' ? 'visible' : 'gone'}}"),
                    width=dv.DivMatchParentSize(),
                    height=dv.DivFixedSize(value=self.height),
                    scale=dv.DivImageScale.FIT,
                ),
            ],
            height=dv.DivFixedSize(value=self.height),
            content_alignment_vertical=dv.DivContentAlignmentVertical.CENTER,
            background=[dv.DivSolidBackground(color="#ECEFF1")],
            border=dv.DivBorder(corner_radius=12),
            actions=[
                dv.DivAction(
                    log_id=f"pick:{self.source}",
                    url=(
                        f"latawiec://pick?variable={quote(self.variable, safe='')}"
                        f"&source={self.source}"
                    ),
                )
            ],
        )


@dataclass(frozen=True)
class TextInput(Component):
    """A text field bound to a screen variable.

    The variable is declared here, so other components can read it with a
    DivKit expression: Text(Expression("Hello, @{name}!")).
    """

    variable: str
    hint: str | None = None
    initial: str = ""
    password: bool = False
    style: Style | None = None

    def _build(self) -> dv.Div:
        hint = _literal(self.hint) if self.hint else None
        return dv.DivInput(
            text_variable=self.variable,
            keyboard_type=dv.DivInputKeyboardType.PASSWORD if self.password else None,
            hint_text=hint,
            # Without a description the input is invisible to screen readers
            # (and to UI tests) on both platforms.
            accessibility=dv.DivAccessibility(description=hint) if hint else None,
            paddings=dv.DivEdgeInsets(top=12, bottom=12, left=16, right=16),
            border=dv.DivBorder(corner_radius=8, stroke=dv.DivStroke(color="#B0BEC5")),
        )


@dataclass(frozen=True)
class Switch(Component):
    """An on/off toggle bound to a boolean screen variable.

    Read it elsewhere with an expression: Text(Expression("@{dark}")) shows
    true/false.
    """

    variable: str
    initial: bool = False
    style: Style | None = None

    def _build(self) -> dv.Div:
        return dv.DivSwitch(
            is_on_variable=self.variable,
            # DivKit's default width is match_parent, and a stretched switch
            # is a fatal error on iOS (SwitchBlock is not resizable).
            width=dv.DivWrapContentSize(),
        )


@dataclass(frozen=True)
class Option:
    """One Select choice; the stored value defaults to the label."""

    label: str
    value: str | None = None


@dataclass(frozen=True)
class Select(Component):
    """A dropdown bound to a string screen variable."""

    variable: str
    options: tuple[Option | str, ...]
    hint: str | None = None
    initial: str = ""
    style: Style | None = None

    def _build(self) -> dv.Div:
        hint = _literal(self.hint) if self.hint else None
        return dv.DivSelect(
            value_variable=self.variable,
            options=[
                dv.DivSelectOption(
                    text=_literal(option.label),
                    value=_literal(option.value if option.value is not None else option.label),
                )
                if isinstance(option, Option)
                else dv.DivSelectOption(text=_literal(option), value=_literal(option))
                for option in self.options
            ],
            hint_text=hint,
            # Same trap as DivInput: without a description the control is
            # invisible to screen readers (and to UI tests) on both platforms.
            accessibility=dv.DivAccessibility(description=hint) if hint else None,
            paddings=dv.DivEdgeInsets(top=12, bottom=12, left=16, right=16),
            border=dv.DivBorder(corner_radius=8, stroke=dv.DivStroke(color="#B0BEC5")),
        )


def _track(color: str) -> dv.DivShapeDrawable:
    return dv.DivShapeDrawable(
        color=color,
        shape=dv.DivRoundedRectangleShape(item_height=dv.DivFixedSize(value=4)),
    )


@dataclass(frozen=True)
class Slider(Component):
    """An integer slider bound to a screen variable; starts at `initial` or `min`.

    DivKit renders no slider without explicit thumb and track drawables, so
    this draws a round thumb and a 4dp track in `color`.
    """

    variable: str
    min: int = 0
    max: int = 100
    initial: int | None = None
    color: str = "#2962FF"
    style: Style | None = None

    def _build(self) -> dv.Div:
        return dv.DivSlider(
            thumb_value_variable=self.variable,
            min_value=self.min,
            max_value=self.max,
            thumb_style=dv.DivShapeDrawable(
                color=self.color,
                shape=dv.DivRoundedRectangleShape(
                    item_width=dv.DivFixedSize(value=24),
                    item_height=dv.DivFixedSize(value=24),
                    corner_radius=dv.DivFixedSize(value=12),
                ),
            ),
            track_active_style=_track(self.color),
            track_inactive_style=_track("#B0BEC5"),
        )


def _taps(button: Button) -> tuple[Action, ...]:
    return tuple(button.on_tap) if isinstance(button.on_tap, (tuple, list)) else (button.on_tap,)


@dataclass(frozen=True)
class Button(Component):
    """DivKit has no button primitive, so this is a tappable, button-styled text."""

    label: str
    on_tap: Action | tuple[Action, ...]
    color: str = "#2962FF"
    text_color: str = "#FFFFFF"
    tap_animation: Literal["fade", "scale", "none"] | None = None
    """The press feedback; DivKit's default is a fade+scale combination."""
    style: Style | None = None

    def _build(self) -> dv.Div:
        feedback = "no_animation" if self.tap_animation == "none" else self.tap_animation
        return dv.DivText(
            text=_literal(self.label),
            text_alignment_horizontal=dv.DivAlignmentHorizontal.CENTER,
            text_color=self.text_color,
            paddings=dv.DivEdgeInsets(top=12, bottom=12, left=20, right=20),
            background=[dv.DivSolidBackground(color=self.color)],
            border=dv.DivBorder(corner_radius=8),
            actions=[tap.to_div_action() for tap in _taps(self)],
            action_animation=(
                dv.DivAnimation(name=dv.DivAnimationName(feedback)) if feedback else None
            ),
        )


class _Container(Component):
    _orientation: ClassVar[dv.DivContainerOrientation]

    def __init__(self, *children: Component, style: Style | None = None) -> None:
        self.children = children
        self.style = style

    def _build(self) -> dv.Div:
        return dv.DivContainer(
            orientation=self._orientation,
            items=[child.to_div() for child in self.children],
        )


class Column(_Container):
    """Children stacked vertically."""

    _orientation = dv.DivContainerOrientation.VERTICAL


class Row(_Container):
    """Children laid out side by side."""

    _orientation = dv.DivContainerOrientation.HORIZONTAL


class Stack(_Container):
    """Children drawn on top of each other; place each with its Style
    align/align_vertical."""

    _orientation = dv.DivContainerOrientation.OVERLAP


class Pager(_Container):
    """Swipeable full-width pages; give it an id and point an Indicator
    at it for dots."""

    def __init__(
        self,
        *children: Component,
        id: str | None = None,
        spacing: int | None = None,
        style: Style | None = None,
    ) -> None:
        super().__init__(*children, style=style)
        self.id = id
        self.spacing = spacing

    def _build(self) -> dv.Div:
        return dv.DivPager(
            id=self.id,
            item_spacing=dv.DivFixedSize(value=self.spacing) if self.spacing is not None else None,
            layout_mode=dv.DivPageSize(page_width=dv.DivPercentageSize(value=100)),
            items=[child.to_div() for child in self.children],
        )


class Tabs(_Container):
    """Tabs inside a screen, each a (title, content) pair — distinct from
    the app-level native bottom bar that Latawiec(tabs=...) declares."""

    def __init__(self, *tabs: tuple[str, Component], style: Style | None = None) -> None:
        super().__init__(*[content for _, content in tabs], style=style)
        self._titles = [title for title, _ in tabs]

    def _build(self) -> dv.Div:
        return dv.DivTabs(
            items=[
                dv.DivTabsItem(title=_literal(title), div=content.to_div())
                for title, content in zip(self._titles, self.children, strict=True)
            ],
        )


class Gallery(_Container):
    """A scrolling list of children.

    Scrolls vertically by default; DivKit's own default is horizontal, so the
    orientation is always emitted explicitly.
    """

    def __init__(
        self,
        *children: Component,
        horizontal: bool = False,
        spacing: int | None = None,
        style: Style | None = None,
    ) -> None:
        super().__init__(*children, style=style)
        self.horizontal = horizontal
        self.spacing = spacing

    def _build(self) -> dv.Div:
        return dv.DivGallery(
            orientation=(
                dv.DivGalleryOrientation.HORIZONTAL
                if self.horizontal
                else dv.DivGalleryOrientation.VERTICAL
            ),
            item_spacing=self.spacing,
            items=[child.to_div() for child in self.children],
        )


class Grid(_Container):
    """Children laid out in fixed columns, row by row."""

    def __init__(self, *children: Component, columns: int, style: Style | None = None) -> None:
        super().__init__(*children, style=style)
        self.columns = columns

    def _build(self) -> dv.Div:
        items: list[dv.Div] = []
        for child in self.children:
            div = child.to_div()
            # DivKit's default width is match_parent, which renders a grid
            # cell empty on both platforms; unset widths become wrap_content.
            if div.width is None:
                div.width = dv.DivWrapContentSize()
            items.append(div)
        return dv.DivGrid(column_count=self.columns, items=items)


@dataclass(frozen=True)
class Indicator(Component):
    """Dots tracking the Pager whose id is `pager`."""

    pager: str
    color: str = "#2962FF"
    inactive_color: str = "#B0BEC5"
    style: Style | None = None

    def _build(self) -> dv.Div:
        return dv.DivIndicator(
            pager_id=self.pager,
            active_item_color=self.color,
            inactive_item_color=self.inactive_color,
        )


@dataclass(frozen=True)
class Marker:
    """A pin on a Map."""

    latitude: float
    longitude: float
    label: str = ""


@dataclass(frozen=True)
class Map(Component):
    """A map the user can pan and zoom, with pins on it.

    Each shell draws it with what the platform already has — MapKit on
    iOS, a tile view on Android — so the map costs the app no dependency
    and no API key. They therefore look different by default; passing
    `tiles` makes both draw the same raster tiles instead:

        Map(52.2297, 21.0122, tiles="https://tile.example.com/{z}/{x}/{y}.png")

    OpenStreetMap's own tile servers, which the Android shell falls back
    to, are a courtesy with a usage policy — a real app points `tiles` at
    its own server or a paid one.
    """

    latitude: float
    longitude: float
    zoom: int = 14
    height: int = 240
    markers: tuple[Marker, ...] = ()
    tiles: str | None = None
    style: Style | None = None

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 90:
            raise ValueError(f"latitude {self.latitude} is outside -90..90")
        if not -180 <= self.longitude <= 180:
            raise ValueError(f"longitude {self.longitude} is outside -180..180")
        if not 1 <= self.zoom <= 20:
            raise ValueError(f"zoom {self.zoom} is outside 1..20")
        if self.tiles is not None:
            # The Android shell builds a real HTTP request out of this, and
            # its client rejects anything else by throwing mid-draw.
            if not self.tiles.startswith(("http://", "https://")):
                raise ValueError(f"tiles {self.tiles!r} is not an http(s) URL")
            # A template without the three placeholders asks one server for
            # one tile forever, which looks like a map that will not load.
            missing = [hole for hole in ("{z}", "{x}", "{y}") if hole not in self.tiles]
            if missing:
                raise ValueError(f"tiles {self.tiles!r} never substitutes {missing[0]}")

    def _build(self) -> dv.Div:
        # DivKit has no map, so the shells render this custom type
        # themselves; the payload below is the whole contract between them.
        return dv.DivCustom(
            custom_type="latawiec_map",
            height=dv.DivFixedSize(value=self.height),
            width=dv.DivMatchParentSize(),
            custom_props={
                "latitude": self.latitude,
                "longitude": self.longitude,
                "zoom": self.zoom,
                "tiles": self.tiles or "",
                "markers": [
                    {
                        "latitude": pin.latitude,
                        "longitude": pin.longitude,
                        "label": pin.label,
                    }
                    for pin in self.markers
                ],
            },
        )


@dataclass(frozen=True)
class Video(Component):
    """A video player fed by URL.

    Both shells play through the platform player (AVPlayer / MediaPlayer),
    so the supported formats are what the system plays — MP4 and HLS cover
    it. DASH needs an Android shell built with -PwithVideo, which carries
    ExoPlayer; see docs/shipping.md.
    """

    url: str
    autoplay: bool = False
    loop: bool = False
    muted: bool = False
    style: Style | None = None
    # Last, so an app written against an earlier release keeps working.
    height: int = 200
    """A video has no size until it loads, and DivKit sizes it to its
    content, so without this the player is zero pixels tall."""

    def _build(self) -> dv.Div:
        # DivKit requires the mime type; derive it from the URL's extension.
        mime, _ = mimetypes.guess_type(self.url)
        return dv.DivVideo(
            height=dv.DivFixedSize(value=self.height),
            video_sources=[
                dv.DivVideoSource(url=_literal(self.url), mime_type=mime or "video/mp4")
            ],
            autostart=True if self.autoplay else None,
            repeatable=True if self.loop else None,
            muted=True if self.muted else None,
        )


@dataclass(frozen=True)
class GifImage(Component):
    """An animated GIF; plain Image shows only its first frame."""

    url: str
    style: Style | None = None

    def _build(self) -> dv.Div:
        return dv.DivGifImage(gif_url=_literal(self.url))


@dataclass(frozen=True)
class Separator(Component):
    """A thin horizontal rule."""

    color: str = "#B0BEC5"
    style: Style | None = None

    def _build(self) -> dv.Div:
        return dv.DivSeparator(
            delimiter_style=dv.DivSeparatorDelimiterStyle(color=self.color),
        )


@dataclass(frozen=True)
class Spacer(Component):
    """Fixed empty space; give it a height in a Column or a width in a Row.

    DivKit has no spacer primitive, so this is a separator drawn transparent.
    """

    height: int | None = None
    width: int | None = None
    style: Style | None = None

    def _build(self) -> dv.Div:
        if self.height is None and self.width is None:
            raise ValueError("Spacer needs a height or a width")
        return dv.DivSeparator(
            width=dv.DivFixedSize(value=self.width) if self.width is not None else None,
            height=dv.DivFixedSize(value=self.height) if self.height is not None else None,
            delimiter_style=dv.DivSeparatorDelimiterStyle(color="#00000000"),
        )


ScreenVariable = dv.StringVariable | dv.BooleanVariable | dv.IntegerVariable


def _declared_variables(node: Component) -> list[tuple[str, ScreenVariable]]:
    if isinstance(node, TextInput | Select):
        # The declared value is evaluated like any other string, so a
        # prefill holding either character needs the same treatment.
        return [
            (node.variable, dv.StringVariable(name=node.variable, value=_literal(node.initial)))
        ]
    if isinstance(node, ImagePicker):
        return [(node.variable, dv.StringVariable(name=node.variable, value=""))]
    if isinstance(node, Switch):
        return [(node.variable, dv.BooleanVariable(name=node.variable, value=node.initial))]
    if isinstance(node, Slider):
        value = node.min if node.initial is None else node.initial
        return [(node.variable, dv.IntegerVariable(name=node.variable, value=value))]
    return []


def _action_variables(node: Component) -> list[tuple[str, ScreenVariable]]:
    """Variables an action writes into, which no component need carry.

    DivKit refuses to assign to a variable a card never declared — the
    write is dropped and every expression reading it renders empty — so an
    action that writes into one declares it here.
    """
    if not isinstance(node, Button):
        return []
    return [
        (tap.variable, dv.StringVariable(name=tap.variable, value=""))
        for tap in _taps(node)
        if isinstance(tap, RequestLocation | SetVariable)
    ]


def _sent_variables(node: Component) -> tuple[str, ...]:
    """Variables an action reads at tap time, which the card has to declare."""
    if not isinstance(node, Button):
        return ()
    return tuple(
        name for tap in _taps(node) if isinstance(tap, Submit | Unlock) for name in tap.send
    )


def _screen_variables(root: Component) -> list[ScreenVariable]:
    # DivKit scopes a variable declared on an element to that element and its
    # descendants, so a control's variable is hoisted to the card, where a
    # sibling Text(Expression("@{name}")) can read it.
    declared: dict[str, ScreenVariable] = {}
    from_actions: dict[str, ScreenVariable] = {}
    sent: list[str] = []
    stack = [root]
    while stack:
        node = stack.pop()
        for name, variable in _declared_variables(node):
            if declared.setdefault(name, variable).dict() != variable.dict():
                raise ValueError(
                    f"variable {name!r} is declared with conflicting types or initial values"
                )
        for name, variable in _action_variables(node):
            from_actions.setdefault(name, variable)
        sent.extend(_sent_variables(node))
        if isinstance(node, _Container):
            stack.extend(reversed(node.children))
    # An action aimed at a control's own variable (a fix dropped into a
    # search box) writes into that declaration instead of fighting it.
    for name, variable in from_actions.items():
        declared.setdefault(name, variable)
    missing = [name for name in sent if name not in declared]
    if missing:
        raise ValueError(
            f"an action on this screen sends {missing[0]!r}, which nothing on it "
            "declares: the tap would evaluate to nothing and silently do nothing "
            "— bind it to a control, or write it first with SetVariable"
        )
    return list(declared.values())


def render(root: Component) -> dict[str, Any]:
    """Build the DivKit card payload a native shell renders."""
    div = root.to_div()
    card = dv.DivData(
        log_id="card",
        states=[dv.DivDataState(state_id=0, div=div)],
        variables=_screen_variables(root) or None,
    )
    return {
        "templates": {tpl.template_name: tpl.template() for tpl in div.related_templates()},
        "card": card.dict(),
    }
