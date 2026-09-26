"""Coupon discount rule. Called directly by carts, checkout, and refunds."""

from __future__ import annotations

from . import catalog


def coupon_discount(lines: list[tuple[str, int, int]], coupon_code: str | None) -> int:
    """Percentage coupon on eligible lines, half-up in cents, never above the subtotal.

    `lines` are (sku, quantity, unit_price_cents).
    """
    coupon = catalog.COUPONS.get(coupon_code) if coupon_code else None
    if coupon is None:
        return 0
    subtotal = 0
    eligible = 0
    for sku, quantity, unit_price in lines:
        amount = quantity * unit_price
        subtotal += amount
        product = catalog.PRODUCTS.get(sku)
        if product is not None and product.coupon_eligible:
            eligible += amount
    return min((eligible * coupon.percent + 50) // 100, subtotal)
