"""Synthetic product and coupon data. All values are fictional."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    unit_price_cents: int
    coupon_eligible: bool


@dataclass(frozen=True)
class Coupon:
    code: str
    percent: int


PRODUCTS: dict[str, Product] = {
    p.sku: p
    for p in (
        Product("TSHIRT", "Logo T-Shirt", 2000, True),
        Product("MUG", "Ceramic Mug", 1250, True),
        Product("HOODIE", "Zip Hoodie", 4999, True),
        Product("STICKER", "Sticker Pack", 199, True),
        Product("GIFTCARD", "Gift Card", 5000, False),
    )
}

COUPONS: dict[str, Coupon] = {
    c.code: c for c in (Coupon("SAVE10", 10), Coupon("SAVE25", 25), Coupon("FULLRIDE", 100))
}


def product_view(product: Product) -> dict:
    return {
        "sku": product.sku,
        "name": product.name,
        "unit_price_cents": product.unit_price_cents,
        "coupon_eligible": product.coupon_eligible,
    }
