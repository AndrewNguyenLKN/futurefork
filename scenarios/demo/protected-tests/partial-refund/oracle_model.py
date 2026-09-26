"""Executable statement of the frozen partial-refund allocation rules (public_interface.rules)."""

from __future__ import annotations


def allocate_line_discounts(weights: list[int], discount: int) -> list[int]:
    """Largest-remainder split of `discount` over lines weighted by `weights`.

    Line i gets floor(D*w_i/W); leftover cents go one each by descending (D*w_i mod W),
    ties by ascending line position. Lines with weight 0 (ineligible) get nothing.
    """
    total = sum(weights)
    if total == 0 or discount == 0:
        return [0] * len(weights)
    shares = [discount * w // total for w in weights]
    remainders = [discount * w % total for w in weights]
    order = sorted(range(len(weights)), key=lambda i: (-remainders[i], i))
    for i in order[: discount - sum(shares)]:
        shares[i] += 1
    return shares


def unit_discount(line_discount: int, quantity: int, already: int, count: int) -> int:
    """Discount carried by refunding units already+1 .. already+count of one line."""
    return line_discount * (already + count) // quantity - line_discount * already // quantity


class RefundModel:
    """lines: (sku, quantity, unit_price_cents, coupon_eligible) in cart order."""

    def __init__(self, lines: list[tuple[str, int, int, bool]], order_discount: int) -> None:
        self.lines = {sku: (q, price) for sku, q, price, _ in lines}
        weights = [q * price if eligible else 0 for _, q, price, eligible in lines]
        self.line_discount = dict(zip((l[0] for l in lines), allocate_line_discounts(weights, order_discount)))
        self.done = {sku: 0 for sku in self.lines}
        self.captured = sum(q * price for _, q, price, _ in lines) - order_discount
        self.refunded = 0

    def refund(self, items: list[tuple[str, int]]) -> dict:
        amounts = {}
        for sku, count in items:
            quantity, price = self.lines[sku]
            discount = unit_discount(self.line_discount[sku], quantity, self.done[sku], count)
            amounts[sku] = count * price - discount
        for sku, count in items:
            self.done[sku] += count
        total = sum(amounts.values())
        self.refunded += total
        return {"items": amounts, "amount_cents": total, "remaining_refundable_cents": self.captured - self.refunded}
