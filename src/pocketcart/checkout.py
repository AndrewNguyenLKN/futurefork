"""Checkout: asks the pricing service for a quote and persists it with the order."""

from __future__ import annotations

import json

from .carts import line_items
from .errors import ApiError
from .pricing import PricingService


def order_view(store, order_id: str) -> dict:
    order = store.get_order(order_id)
    if order is None:
        raise ApiError(404, "order_not_found", f"order {order_id} does not exist")
    pricing = store.order_pricing(order)
    return {
        "order_id": order["order_id"],
        "cart_id": order["cart_id"],
        "status": order["status"],
        "items": [
            {"sku": sku, "quantity": q, "unit_price_cents": p, "line_total_cents": q * p}
            for sku, q, p in store.order_lines(order_id)
        ],
        "coupon_id": pricing.coupon_id,
        "subtotal_cents": pricing.subtotal_cents,
        "discount_cents": pricing.discount_cents,
        "total_cents": pricing.total_cents,
        "payment": {"payment_id": order["payment_id"], "captured_cents": order["captured_cents"]},
    }


def checkout(store, pricing_service: PricingService, gateway, cart_id: str, key: str) -> tuple[dict, bool]:
    prior = store.get_idempotent(key)
    if prior is not None:
        if prior["cart_id"] != cart_id:
            raise ApiError(409, "idempotency_key_reuse", "Idempotency-Key was used for a different cart")
        return json.loads(prior["response"]), False

    cart = store.get_cart(cart_id)
    if cart is None:
        raise ApiError(404, "cart_not_found", f"cart {cart_id} does not exist")
    if cart["status"] != "open":
        raise ApiError(409, "cart_closed", f"cart {cart_id} is already checked out")
    lines = line_items(store, cart_id)
    if not lines:
        raise ApiError(422, "empty_cart", f"cart {cart_id} has no items")

    pricing = pricing_service.price(lines, cart["coupon_id"])
    order_id = store.next_id("order")
    payment = gateway.capture(order_id, pricing.total_cents)
    store.save_order(order_id, cart_id, pricing, payment, lines)
    store.close_cart(cart_id)
    order = order_view(store, order_id)
    store.put_idempotent(key, cart_id, json.dumps(order))
    return order, True
