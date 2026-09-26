"""Black-box HTTP client for evaluator tests. Uses only the public WSGI entry point."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass


@dataclass
class Response:
    status: int
    body: dict
    raw: bytes


class Client:
    def __init__(self, app) -> None:
        self.app = app
        self._keys = 0

    def request(self, method, path, body=None, headers=None) -> Response:
        payload = json.dumps(body).encode() if body is not None else b""
        environ = {
            "REQUEST_METHOD": method, "PATH_INFO": path,
            "CONTENT_LENGTH": str(len(payload)), "wsgi.input": io.BytesIO(payload),
        }
        for name, value in (headers or {}).items():
            environ["HTTP_" + name.upper().replace("-", "_")] = value
        seen = {}
        raw = b"".join(self.app(environ, lambda status, hdrs: seen.update(status=int(status.split()[0]))))
        return Response(seen["status"], json.loads(raw), raw)

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, body=None, headers=None):
        return self.request("POST", path, body, headers)

    def checkout(self, cart_id, key=None) -> Response:
        self._keys += 1
        return self.post("/checkout", {"cart_id": cart_id}, {"Idempotency-Key": key or f"eval-{self._keys}"})


def expect(response: Response, status: int, code: str | None = None) -> dict:
    """Assert status (and error code); returns the body. Failures show the body."""
    assert response.status == status, f"expected HTTP {status}, got {response.status}: {response.body}"
    if code is not None:
        assert response.body.get("error", {}).get("code") == code, f"expected error {code!r}: {response.body}"
    return response.body


def field(body: dict, key: str):
    """Read a key that the future behavior adds; a missing key is an assertion failure."""
    assert key in body, f"expected key {key!r} in response, got {sorted(body)}"
    return body[key]
