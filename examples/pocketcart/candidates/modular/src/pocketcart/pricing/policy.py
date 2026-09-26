"""Discount policy interface and the percentage-coupon implementation."""

from __future__ import annotations

from typing import Protocol, Sequence

from .. import catalog
from .models import DiscountResult, LineItem


class DiscountPolicy(Protocol):
    def knows_coupon(self, code: str) -> bool: ...

    def evaluate(self, lines: Sequence[LineItem], coupon_code: str | None) -> DiscountResult: ...


class PercentageCouponPolicy:
    """Percentage coupon on eligible lines, half-up in cents."""

    def knows_coupon(self, code: str) -> bool:
        return code in catalog.COUPONS

    def evaluate(self, lines: Sequence[LineItem], coupon_code: str | None) -> DiscountResult:
        coupon = catalog.COUPONS.get(coupon_code) if coupon_code else None
        if coupon is None:
            return DiscountResult(0, None)
        eligible = sum(line.amount_cents for line in lines if line.coupon_eligible)
        return DiscountResult((eligible * coupon.percent + 50) // 100, coupon.code)
