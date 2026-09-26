"""Executable statement of the frozen ordered-discount rules (public_interface.rules)."""

from __future__ import annotations

# name -> (automatic percent, application order, max_discount_cents)
ORGANIZATIONS = {
    "org-acme": (20, ("organization", "coupon"), 3000),
    "org-globex": (15, ("coupon", "organization"), 3000),
    "org-initech": (30, ("organization", "coupon"), 500),
}
COUPON_PERCENT = {"SAVE10": 10, "SAVE25": 25, "FULLRIDE": 100}


def half_up(base: int, percent: int) -> int:
    return (base * percent + 50) // 100


def compose(eligible: int, subtotal: int, organization_id: str | None, coupon: str | None) -> list[dict]:
    """Components in application order. Each applies to what the earlier ones left of the
    eligible amount (computed uncapped); the cap is consumed in application order."""
    if organization_id is None:
        percent, order, cap = 0, ("coupon",), subtotal
    else:
        percent, order, cap = ORGANIZATIONS[organization_id]
        cap = min(cap, subtotal)
    base, cap_left, out = eligible, cap, []
    for source in order:
        if source == "organization" and organization_id is not None:
            pct, ident = percent, organization_id
        elif source == "coupon" and coupon is not None:
            pct, ident = COUPON_PERCENT[coupon], coupon
        else:
            continue
        raw = half_up(base, pct)
        base -= raw
        amount = min(raw, cap_left)
        cap_left -= amount
        out.append({"source": source, "id": ident, "amount_cents": amount})
    return out
