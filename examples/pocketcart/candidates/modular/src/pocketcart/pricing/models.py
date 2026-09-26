"""Pricing value objects: what a price quote is, independent of how it was derived."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineItem:
    sku: str
    quantity: int
    unit_price_cents: int
    coupon_eligible: bool

    @property
    def amount_cents(self) -> int:
        return self.quantity * self.unit_price_cents


@dataclass(frozen=True)
class DiscountResult:
    amount_cents: int
    coupon_id: str | None


@dataclass(frozen=True)
class PricingResult:
    """The pricing decision made at quote time. Persisted with the order."""

    subtotal_cents: int
    discount_cents: int
    total_cents: int
    coupon_id: str | None

    def to_dict(self) -> dict:
        return {
            "subtotal_cents": self.subtotal_cents,
            "discount_cents": self.discount_cents,
            "total_cents": self.total_cents,
            "coupon_id": self.coupon_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PricingResult":
        return cls(**data)
