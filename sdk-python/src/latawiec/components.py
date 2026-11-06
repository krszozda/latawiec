from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

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


class Column(Component):
    """Children stacked vertically."""

    def __init__(self, *children: Component) -> None:
        self.children = children

    def to_div(self) -> dv.Div:
        return dv.DivContainer(
            orientation=dv.DivContainerOrientation.VERTICAL,
            items=[child.to_div() for child in self.children],
        )


def render(root: Component) -> dict[str, Any]:
    """Build the DivKit card payload a native shell renders."""
    return dv.make_div(root.to_div())
