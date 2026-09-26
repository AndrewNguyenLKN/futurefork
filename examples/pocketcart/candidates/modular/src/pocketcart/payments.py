"""Deterministic fake payment gateway. No network, no real payment data."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Payment:
    payment_id: str
    captured_cents: int


class FakeGateway:
    def __init__(self) -> None:
        self._count = 0

    def capture(self, order_id: str, amount_cents: int) -> Payment:
        if amount_cents < 0:
            raise ValueError("cannot capture a negative amount")
        self._count += 1
        return Payment(f"pay_{self._count:04d}", amount_cents)
