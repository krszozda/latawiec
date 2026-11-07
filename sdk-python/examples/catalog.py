"""Example Latawiec app: screens generated from data. Run from sdk-python/:

    uv run uvicorn examples.catalog:app --host 0.0.0.0

One list screen plus one screen per product, all registered in a loop —
screens are ordinary Python over ordinary data.
"""

from dataclasses import dataclass
from datetime import datetime
from functools import partial

import latawiec as lt


@dataclass(frozen=True)
class Product:
    slug: str
    name: str
    price: str
    photo: str


PRODUCTS = [
    Product("box", "Box kite", "$29", "https://picsum.photos/id/1003/800/500"),
    Product("delta", "Delta kite", "$35", "https://picsum.photos/id/1015/800/500"),
    Product("stunt", "Stunt kite", "$59", "https://picsum.photos/id/1036/800/500"),
]

app = lt.Latawiec()


@app.screen("home")
def home() -> lt.Component:
    listing = [
        item
        for product in PRODUCTS
        for item in (
            lt.Text(f"{product.name} — {product.price}", size=20),
            lt.Button("View", on_tap=lt.Navigate(product.slug)),
        )
    ]
    return lt.Column(
        lt.Text("Kite shop", size=28),
        *listing,
        lt.Text(f"Rendered server-side at {datetime.now():%H:%M:%S}"),
    )


def product_screen(product: Product) -> lt.Component:
    return lt.Column(
        lt.Image(product.photo),
        lt.Text(product.name, size=28),
        lt.Text(product.price, size=20),
        lt.Text("System back returns to the list."),
    )


for product in PRODUCTS:
    app.screen(product.slug)(partial(product_screen, product))
