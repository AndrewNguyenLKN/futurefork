"""Executable statement of the frozen organization-pricing rules (public_interface.rules)."""

from __future__ import annotations

# name -> (policy_id, percent of coupon-eligible subtotal, max_discount_cents)
ORGANIZATIONS = {
    "org-acme": ("acme-standard", 20, 1500),
    "org-globex": ("globex-volume", 30, 500),
}


def organization_discount(organization_id: str, eligible_cents: int, subtotal_cents: int) -> int:
    _, percent, cap = ORGANIZATIONS[organization_id]
    return min((eligible_cents * percent + 50) // 100, cap, subtotal_cents)
