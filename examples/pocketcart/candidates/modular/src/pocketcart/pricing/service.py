"""PricingService: the single place a price quote is produced."""

from __future__ import annotations

from typing import Sequence

from .models import LineItem, PricingResult
from .policy import DiscountPolicy


class PricingService:
    def __init__(self, policy: DiscountPolicy) -> None:
        self._policy = policy

    def knows_coupon(self, code: str) -> bool:
        return self._policy.knows_coupon(code)

    def price(self, lines: Sequence[LineItem], coupon_code: str | None) -> PricingResult:
        subtotal = sum(line.amount_cents for line in lines)
        result = self._policy.evaluate(lines, coupon_code)
        discount = min(result.amount_cents, subtotal)
        return PricingResult(subtotal, discount, subtotal - discount, result.coupon_id)
