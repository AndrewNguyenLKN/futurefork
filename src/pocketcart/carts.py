"""Cart operations. Quotes come from the pricing service."""

from __future__ import annotations

from . import catalog
from .errors import ApiError
from .pricing import LineItem, PricingService
from .validation import MAX_QUANTITY


def _existing_cart(store, cart_id: str):
    cart = store.get_cart(cart_id)
    if cart is None:
        raise ApiError(404, "cart_not_found", f"cart {cart_id} does not exist")
    return cart


def line_items(store, cart_id: str) -> list[LineItem]:
    lines = []
    for sku, quantity in store.cart_items(cart_id):
        product = catalog.PRODUCTS[sku]
        lines.append(LineItem(sku, quantity, product.unit_price_cents, product.coupon_eligible))
    return lines


def create_cart(store) -> dict:
    return {"cart_id": store.create_cart()}


def cart_view(store, pricing: PricingService, cart_id: str) -> dict:
    cart = _existing_cart(store, cart_id)
    lines = line_items(store, cart_id)
    quote = pricing.price(lines, cart["coupon_id"])
    return {
        "cart_id": cart_id,
        "status": cart["status"],
        "items": [
            {"sku": l.sku, "quantity": l.quantity, "unit_price_cents": l.unit_price_cents,
             "line_total_cents": l.amount_cents}
            for l in lines
        ],
        "coupon_id": cart["coupon_id"],
        **{k: v for k, v in quote.to_dict().items() if k != "coupon_id"},
    }


def add_item(store, pricing: PricingService, cart_id: str, sku: str, quantity: int) -> dict:
    cart = _existing_cart(store, cart_id)
    if cart["status"] != "open":
        raise ApiError(409, "cart_closed", f"cart {cart_id} is already checked out")
    if sku not in catalog.PRODUCTS:
        raise ApiError(422, "unknown_sku", f"unknown sku {sku}")
    if dict(store.cart_items(cart_id)).get(sku, 0) + quantity > MAX_QUANTITY:
        raise ApiError(422, "invalid_quantity", f"quantity must be an integer from 1 to {MAX_QUANTITY}")
    store.add_item(cart_id, sku, quantity)
    return cart_view(store, pricing, cart_id)


def apply_coupon(store, pricing: PricingService, cart_id: str, code: str) -> dict:
    cart = _existing_cart(store, cart_id)
    if cart["status"] != "open":
        raise ApiError(409, "cart_closed", f"cart {cart_id} is already checked out")
    if not pricing.knows_coupon(code):
        raise ApiError(422, "unknown_coupon", f"unknown coupon {code}")
    store.set_coupon(cart_id, code)
    return cart_view(store, pricing, cart_id)
