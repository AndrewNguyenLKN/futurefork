"""Cart operations. The quote applies the coupon rule directly."""

from __future__ import annotations

from . import catalog, discounts
from .errors import ApiError
from .validation import MAX_QUANTITY


def _open_cart(store, cart_id: str):
    cart = store.get_cart(cart_id)
    if cart is None:
        raise ApiError(404, "cart_not_found", f"cart {cart_id} does not exist")
    return cart


def _live_lines(store, cart_id: str) -> list[tuple[str, int, int]]:
    return [
        (sku, quantity, catalog.PRODUCTS[sku].unit_price_cents)
        for sku, quantity in store.cart_items(cart_id)
    ]


def create_cart(store) -> dict:
    return {"cart_id": store.create_cart()}


def cart_view(store, cart_id: str) -> dict:
    cart = _open_cart(store, cart_id)
    lines = _live_lines(store, cart_id)
    subtotal = sum(quantity * price for _, quantity, price in lines)
    discount = discounts.coupon_discount(lines, cart["coupon_id"])
    return {
        "cart_id": cart_id,
        "status": cart["status"],
        "items": [
            {"sku": sku, "quantity": q, "unit_price_cents": p, "line_total_cents": q * p}
            for sku, q, p in lines
        ],
        "coupon_id": cart["coupon_id"],
        "subtotal_cents": subtotal,
        "discount_cents": discount,
        "total_cents": subtotal - discount,
    }


def add_item(store, cart_id: str, sku: str, quantity: int) -> dict:
    cart = _open_cart(store, cart_id)
    if cart["status"] != "open":
        raise ApiError(409, "cart_closed", f"cart {cart_id} is already checked out")
    if sku not in catalog.PRODUCTS:
        raise ApiError(422, "unknown_sku", f"unknown sku {sku}")
    current = dict(store.cart_items(cart_id)).get(sku, 0)
    if current + quantity > MAX_QUANTITY:
        raise ApiError(422, "invalid_quantity", f"quantity must be an integer from 1 to {MAX_QUANTITY}")
    store.add_item(cart_id, sku, quantity)
    return cart_view(store, cart_id)


def apply_coupon(store, cart_id: str, code: str) -> dict:
    cart = _open_cart(store, cart_id)
    if cart["status"] != "open":
        raise ApiError(409, "cart_closed", f"cart {cart_id} is already checked out")
    if code not in catalog.COUPONS:
        raise ApiError(422, "unknown_coupon", f"unknown coupon {code}")
    store.set_coupon(cart_id, code)
    return cart_view(store, cart_id)
