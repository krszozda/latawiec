from __future__ import annotations

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
    style: Style | None = None

    def _build(self) -> dv.Div:
        return dv.DivInput(
            text_variable=self.variable,
            hint_text=self.hint,
            # Without a description the input is invisible to screen readers
            # (and to UI tests) on both platforms.
            accessibility=dv.DivAccessibility(description=self.hint) if self.hint else None,
            paddings=dv.DivEdgeInsets(top=12, bottom=12, left=16, right=16),
            border=dv.DivBorder(corner_radius=8, stroke=dv.DivStroke(color="#B0BEC5")),
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


def _screen_variables(root: Component) -> list[dv.StringVariable]:
    # DivKit scopes a variable declared on an element to that element and its
    # descendants, so an input's variable is hoisted to the card, where sibling
    # expressions like Text("@{name}") can read it.
    initials: dict[str, str] = {}
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, TextInput):
            if initials.setdefault(node.variable, node.initial) != node.initial:
                raise ValueError(
                    f"variable {node.variable!r} is declared with conflicting initial values"
                )
        elif isinstance(node, _Container):
            stack.extend(reversed(node.children))
    return [dv.StringVariable(name=name, value=value) for name, value in initials.items()]


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
