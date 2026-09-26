"""Full refund: re-derives the refundable amount from the order lines and coupon."""

from __future__ import annotations

from . import discounts
from .errors import ApiError


def refund_order(store, order_id: str) -> dict:
    order = store.get_order(order_id)
    if order is None:
        raise ApiError(404, "order_not_found", f"order {order_id} does not exist")
    if order["status"] == "refunded":
        raise ApiError(409, "already_refunded", f"order {order_id} was already refunded")
    lines = store.order_lines(order_id)
    subtotal = sum(quantity * price for _, quantity, price in lines)
    refundable = subtotal - discounts.coupon_discount(lines, order["coupon_id"])
    amount = min(refundable, order["captured_cents"])
    refund_id = store.next_id("ref")
    store.save_refund(refund_id, order_id, amount)
    return {"refund_id": refund_id, "order_id": order_id, "status": "refunded", "amount_cents": amount}
