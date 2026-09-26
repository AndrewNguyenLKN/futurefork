"""HTTP-level test client: drives the WSGI app directly, no sockets."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass

import pytest

from pocketcart import create_app


@dataclass
class Response:
    status: int
    body: dict
    raw: bytes


class Client:
    def __init__(self, app) -> None:
        self.app = app

    def request(self, method: str, path: str, body=None, headers=None, raw_body: bytes | None = None) -> Response:
        payload = raw_body if raw_body is not None else (json.dumps(body).encode() if body is not None else b"")
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "CONTENT_LENGTH": str(len(payload)),
            "wsgi.input": io.BytesIO(payload),
        }
        for name, value in (headers or {}).items():
            environ["HTTP_" + name.upper().replace("-", "_")] = value
        captured = {}

        def start_response(status, response_headers):
            captured["status"] = int(status.split()[0])

        raw = b"".join(self.app(environ, start_response))
        return Response(captured["status"], json.loads(raw), raw)

    def get(self, path: str) -> Response:
        return self.request("GET", path)

    def post(self, path: str, body=None, **kwargs) -> Response:
        return self.request("POST", path, body, **kwargs)

    # --- scenario helpers -------------------------------------------------
    def cart_with(self, items: dict[str, int], coupon: str | None = None) -> str:
        cart_id = self.post("/carts").body["cart_id"]
        for sku, quantity in items.items():
            assert self.post(f"/carts/{cart_id}/items", {"sku": sku, "quantity": quantity}).status == 200
        if coupon:
            assert self.post(f"/carts/{cart_id}/coupon", {"code": coupon}).status == 200
        return cart_id

    def checkout(self, cart_id: str, key: str = "key-1") -> Response:
        return self.post("/checkout", {"cart_id": cart_id}, headers={"Idempotency-Key": key})

    def order_with(self, items: dict[str, int], coupon: str | None = None, key: str = "key-1") -> dict:
        response = self.checkout(self.cart_with(items, coupon), key)
        assert response.status == 201, response.body
        return response.body


@pytest.fixture
def client() -> Client:
    return Client(create_app())
