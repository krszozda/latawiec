from __future__ import annotations

import mimetypes
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Literal
from urllib.parse import quote

import pydivkit as dv

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
        return div


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
            text=self.text,
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
    url: str
    style: Style | None = None

    def _build(self) -> dv.Div:
        return dv.DivImage(image_url=self.url)


@dataclass(frozen=True)
class Navigate:
    """Tap action: ask the shell to fetch and show another screen."""

    screen: str

    def to_div_action(self) -> dv.DivAction:
        return dv.DivAction(
            log_id=f"navigate:{self.screen}",
            url=f"latawiec://navigate?screen={quote(self.screen, safe='')}",
        )


@dataclass(frozen=True)
class SetVariable:
    """Tap action: assign a string to a screen variable, on the device."""

    variable: str
    value: str

    def to_div_action(self) -> dv.DivAction:
        return dv.DivAction(
            log_id=f"set:{self.variable}",
            typed=dv.DivActionSetVariable(
                variable_name=self.variable,
                value=dv.StringValue(value=self.value),
            ),
        )


@dataclass(frozen=True)
class Submit:
    """Tap action: POST the named screen variables to a server action handler.

    Variable values travel inside the action URL as @{encodeUri(...)}
    expressions, which DivKit evaluates at tap time — the shell only parses
    query parameters and never reads variables itself.
    """

    action: str
    send: tuple[str, ...]

    def to_div_action(self) -> dv.DivAction:
        query = "".join(f"&{name}=@{{encodeUri({name})}}" for name in self.send)
        return dv.DivAction(
            log_id=f"submit:{self.action}",
            url=f"latawiec://submit?action={quote(self.action, safe='')}{query}",
        )


Action = Navigate | SetVariable | Submit


@dataclass(frozen=True)
class TextInput(Component):
    """A text field bound to a screen variable.

    The variable is declared here, so other components can read it with a
    DivKit expression: Text("Hello, @{name}!").
    """

    variable: str
    hint: str | None = None
    initial: str = ""
    password: bool = False
    style: Style | None = None

    def _build(self) -> dv.Div:
        return dv.DivInput(
            text_variable=self.variable,
            keyboard_type=dv.DivInputKeyboardType.PASSWORD if self.password else None,
            hint_text=self.hint,
            # Without a description the input is invisible to screen readers
            # (and to UI tests) on both platforms.
            accessibility=dv.DivAccessibility(description=self.hint) if self.hint else None,
            paddings=dv.DivEdgeInsets(top=12, bottom=12, left=16, right=16),
            border=dv.DivBorder(corner_radius=8, stroke=dv.DivStroke(color="#B0BEC5")),
        )


@dataclass(frozen=True)
class Switch(Component):
    """An on/off toggle bound to a boolean screen variable.

    Read it elsewhere with an expression: Text("@{dark}") shows true/false.
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
        return dv.DivSelect(
            value_variable=self.variable,
            options=[
                dv.DivSelectOption(
                    text=option.label,
                    value=option.value if option.value is not None else option.label,
                )
                if isinstance(option, Option)
                else dv.DivSelectOption(text=option, value=option)
                for option in self.options
            ],
            hint_text=self.hint,
            # Same trap as DivInput: without a description the control is
            # invisible to screen readers (and to UI tests) on both platforms.
            accessibility=dv.DivAccessibility(description=self.hint) if self.hint else None,
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


@dataclass(frozen=True)
class Button(Component):
    """DivKit has no button primitive, so this is a tappable, button-styled text."""

    label: str
    on_tap: Action
    color: str = "#2962FF"
    text_color: str = "#FFFFFF"
    style: Style | None = None

    def _build(self) -> dv.Div:
        return dv.DivText(
            text=self.label,
            text_alignment_horizontal=dv.DivAlignmentHorizontal.CENTER,
            text_color=self.text_color,
            paddings=dv.DivEdgeInsets(top=12, bottom=12, left=20, right=20),
            background=[dv.DivSolidBackground(color=self.color)],
            border=dv.DivBorder(corner_radius=8),
            actions=[self.on_tap.to_div_action()],
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
                dv.DivTabsItem(title=title, div=content.to_div())
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
class Video(Component):
    """A video player fed by URL (iOS plays today; Android awaits a player)."""

    url: str
    autoplay: bool = False
    loop: bool = False
    muted: bool = False
    style: Style | None = None

    def _build(self) -> dv.Div:
        # DivKit requires the mime type; derive it from the URL's extension.
        mime, _ = mimetypes.guess_type(self.url)
        return dv.DivVideo(
            video_sources=[dv.DivVideoSource(url=self.url, mime_type=mime or "video/mp4")],
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
        return dv.DivGifImage(gif_url=self.url)


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


def _declared_variable(node: Component) -> tuple[str, ScreenVariable] | None:
    if isinstance(node, TextInput | Select):
        return node.variable, dv.StringVariable(name=node.variable, value=node.initial)
    if isinstance(node, Switch):
        return node.variable, dv.BooleanVariable(name=node.variable, value=node.initial)
    if isinstance(node, Slider):
        value = node.min if node.initial is None else node.initial
        return node.variable, dv.IntegerVariable(name=node.variable, value=value)
    return None


def _screen_variables(root: Component) -> list[ScreenVariable]:
    # DivKit scopes a variable declared on an element to that element and its
    # descendants, so a control's variable is hoisted to the card, where
    # sibling expressions like Text("@{name}") can read it.
    declared: dict[str, ScreenVariable] = {}
    stack = [root]
    while stack:
        node = stack.pop()
        if (found := _declared_variable(node)) is not None:
            name, variable = found
            if declared.setdefault(name, variable).dict() != variable.dict():
                raise ValueError(
                    f"variable {name!r} is declared with conflicting types or initial values"
                )
        if isinstance(node, _Container):
            stack.extend(reversed(node.children))
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
