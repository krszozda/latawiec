"""Example Latawiec app: screens generated from data. Run from sdk-python/:

    uv run uvicorn examples.catalog:app --host 0.0.0.0

One scrolling list screen plus a routed product screen — "product/{id}"
captures the id from the path, so one builder serves every product.
"""

from dataclasses import dataclass
from datetime import datetime

import latawiec as lt


@dataclass(frozen=True)
class Product:
    slug: str
    name: str
    price: str
    photo: str


PRODUCTS = {
    product.slug: product
    for product in (
        Product("box", "Box kite", "$29", "https://picsum.photos/id/1003/800/500"),
        Product("delta", "Delta kite", "$35", "https://picsum.photos/id/1015/800/500"),
        Product("stunt", "Stunt kite", "$59", "https://picsum.photos/id/1036/800/500"),
    )
}

app = lt.Latawiec()

GUTTER = lt.Edges(left=16, right=16)


def product_card(product: Product) -> lt.Component:
    return lt.Column(
        lt.Image(product.photo, style=lt.Style(corner_radius=12)),
        lt.Text(product.name, size=20, weight="medium", style=lt.Style(margin=lt.Edges(top=8))),
        lt.Text(product.price, color="#2962FF", weight="bold"),
        lt.Button(
            "View",
            on_tap=lt.Navigate(f"product/{product.slug}"),
            style=lt.Style(margin=lt.Edges(top=8)),
        ),
        style=lt.Style(padding=12, margin=GUTTER, background="#F5F5F5", corner_radius=16),
    )


@app.screen("home")
def home() -> lt.Component:
    return lt.Gallery(
        lt.Text(
            "Kite shop",
            size=28,
            weight="bold",
            # Clears the status bar: the shells render edge to edge.
            style=lt.Style(margin=lt.Edges(top=48, left=16, right=16, bottom=8)),
        ),
        *[product_card(product) for product in PRODUCTS.values()],
        lt.Text(
            f"Rendered server-side at {datetime.now():%H:%M:%S}",
            color="#757575",
            style=lt.Style(margin=16),
        ),
        spacing=8,
    )


@app.screen("product/{id}")
def product_screen(ctx: lt.Context) -> lt.Component:
    product = PRODUCTS.get(ctx.params["id"])
    if product is None:
        return lt.Column(lt.Text("No such product.", style=lt.Style(margin=48)))
    return lt.Column(
        lt.Image(product.photo),
        lt.Text(product.name, size=28, weight="bold", style=lt.Style(margin=GUTTER)),
        lt.Text(product.price, size=20, color="#2962FF", style=lt.Style(margin=GUTTER)),
        lt.Separator(style=lt.Style(margin=lt.Edges(top=12, left=16, right=16))),
        lt.Text("System back returns to the list.", style=lt.Style(margin=16)),
    )
