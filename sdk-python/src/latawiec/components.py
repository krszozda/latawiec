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
class Button(Component):
    """DivKit has no button primitive, so this is a tappable, button-styled text."""

    label: str
    on_tap: Navigate

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


def render(root: Component) -> dict[str, Any]:
    """Build the DivKit card payload a native shell renders."""
    return dv.make_div(root.to_div())
