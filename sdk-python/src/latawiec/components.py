from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar
from urllib.parse import quote

import pydivkit as dv


class Component(ABC):
    """A node of the UI tree."""

    @abstractmethod
    def to_div(self) -> dv.Div: ...


@dataclass(frozen=True)
class Text(Component):
    text: str
    size: int | None = None

    def to_div(self) -> dv.Div:
        return dv.DivText(text=self.text, font_size=self.size)


@dataclass(frozen=True)
class Image(Component):
    url: str

    def to_div(self) -> dv.Div:
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

    def to_div(self) -> dv.Div:
        return dv.DivInput(
            text_variable=self.variable,
            hint_text=self.hint,
            paddings=dv.DivEdgeInsets(top=12, bottom=12, left=16, right=16),
            border=dv.DivBorder(corner_radius=8, stroke=dv.DivStroke(color="#B0BEC5")),
        )


@dataclass(frozen=True)
class Button(Component):
    """DivKit has no button primitive, so this is a tappable, button-styled text."""

    label: str
    on_tap: Action

    def to_div(self) -> dv.Div:
        return dv.DivText(
            text=self.label,
            text_alignment_horizontal=dv.DivAlignmentHorizontal.CENTER,
            text_color="#FFFFFF",
            paddings=dv.DivEdgeInsets(top=12, bottom=12, left=20, right=20),
            background=[dv.DivSolidBackground(color="#2962FF")],
            border=dv.DivBorder(corner_radius=8),
            actions=[self.on_tap.to_div_action()],
        )


class _Container(Component):
    _orientation: ClassVar[dv.DivContainerOrientation]

    def __init__(self, *children: Component) -> None:
        self.children = children

    def to_div(self) -> dv.Div:
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
