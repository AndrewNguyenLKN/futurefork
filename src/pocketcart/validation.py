"""Request-shape validation shared by both HTTP entry points."""

from __future__ import annotations

from .errors import ApiError

MAX_QUANTITY = 99


def _text(body: dict, key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(422, "invalid_request", f"'{key}' must be a non-empty string")
    return value


def item_request(body: dict) -> tuple[str, int]:
    sku = _text(body, "sku")
    quantity = body.get("quantity")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MAX_QUANTITY:
        raise ApiError(422, "invalid_quantity", f"quantity must be an integer from 1 to {MAX_QUANTITY}")
    return sku, quantity


def coupon_request(body: dict) -> str:
    return _text(body, "code")


def checkout_request(body: dict, idempotency_key: str | None) -> tuple[str, str]:
    if idempotency_key is None or not idempotency_key.strip():
        raise ApiError(400, "missing_idempotency_key", "Idempotency-Key header is required")
    return _text(body, "cart_id"), idempotency_key.strip()
