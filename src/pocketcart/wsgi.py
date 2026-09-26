"""HTTP layer: routing, JSON encoding, and error mapping (WSGI)."""

from __future__ import annotations

import json
import re
from http import HTTPStatus

from . import catalog, validation
from .errors import ApiError

_ROUTES = [
    ("GET", re.compile(r"^/products$"), "products"),
    ("POST", re.compile(r"^/carts$"), "create_cart"),
    ("GET", re.compile(r"^/carts/([^/]+)$"), "get_cart"),
    ("POST", re.compile(r"^/carts/([^/]+)/items$"), "add_item"),
    ("POST", re.compile(r"^/carts/([^/]+)/coupon$"), "apply_coupon"),
    ("POST", re.compile(r"^/checkout$"), "checkout"),
    ("GET", re.compile(r"^/orders/([^/]+)$"), "get_order"),
    ("POST", re.compile(r"^/orders/([^/]+)/refund$"), "refund_order"),
]


def encode(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


class WsgiApp:
    def __init__(self, api) -> None:
        self.api = api

    def __call__(self, environ, start_response):
        try:
            status, payload = self._dispatch(environ)
        except ApiError as err:
            status, payload = err.status, {"error": {"code": err.code, "message": err.message}}
        body = encode(payload)
        start_response(
            f"{status} {HTTPStatus(status).phrase}",
            [("Content-Type", "application/json"), ("Content-Length", str(len(body)))],
        )
        return [body]

    def _dispatch(self, environ) -> tuple[int, dict]:
        method, path = environ["REQUEST_METHOD"], environ.get("PATH_INFO", "")
        allowed = []
        for route_method, pattern, name in _ROUTES:
            match = pattern.match(path)
            if not match:
                continue
            if route_method != method:
                allowed.append(route_method)
                continue
            body = self._read_json(environ) if method == "POST" else {}
            return getattr(self, f"_h_{name}")(body, environ, *match.groups())
        if allowed:
            raise ApiError(405, "method_not_allowed", f"{method} is not allowed for {path}")
        raise ApiError(404, "not_found", f"no route for {path}")

    @staticmethod
    def _read_json(environ) -> dict:
        length = int(environ.get("CONTENT_LENGTH") or 0)
        raw = environ["wsgi.input"].read(length) if length else b""
        if not raw.strip():
            return {}
        try:
            body = json.loads(raw)
        except ValueError:
            raise ApiError(400, "invalid_json", "request body is not valid JSON") from None
        if not isinstance(body, dict):
            raise ApiError(400, "invalid_json", "request body must be a JSON object")
        return body

    def _h_products(self, body, environ):
        return 200, {"products": [catalog.product_view(p) for p in catalog.PRODUCTS.values()]}

    def _h_create_cart(self, body, environ):
        return 201, self.api.create_cart()

    def _h_get_cart(self, body, environ, cart_id):
        return 200, self.api.get_cart(cart_id)

    def _h_add_item(self, body, environ, cart_id):
        sku, quantity = validation.item_request(body)
        return 200, self.api.add_item(cart_id, sku, quantity)

    def _h_apply_coupon(self, body, environ, cart_id):
        return 200, self.api.apply_coupon(cart_id, validation.coupon_request(body))

    def _h_checkout(self, body, environ):
        cart_id, key = validation.checkout_request(body, environ.get("HTTP_IDEMPOTENCY_KEY"))
        order, created = self.api.checkout(cart_id, key)
        return (201 if created else 200), order

    def _h_get_order(self, body, environ, order_id):
        return 200, self.api.get_order(order_id)

    def _h_refund_order(self, body, environ, order_id):
        return 201, self.api.refund_order(order_id)
