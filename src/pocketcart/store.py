"""SQLite persistence (in-memory). Orders persist the full pricing result."""

from __future__ import annotations

import json
import sqlite3

from .pricing import PricingResult

_SCHEMA = """
CREATE TABLE carts (cart_id TEXT PRIMARY KEY, coupon_id TEXT, status TEXT NOT NULL);
CREATE TABLE cart_items (
    cart_id TEXT NOT NULL, position INTEGER NOT NULL, sku TEXT NOT NULL, quantity INTEGER NOT NULL,
    PRIMARY KEY (cart_id, sku)
);
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY, cart_id TEXT NOT NULL, pricing_json TEXT NOT NULL,
    status TEXT NOT NULL, payment_id TEXT NOT NULL, captured_cents INTEGER NOT NULL
);
CREATE TABLE order_items (
    order_id TEXT NOT NULL, position INTEGER NOT NULL, sku TEXT NOT NULL,
    quantity INTEGER NOT NULL, unit_price_cents INTEGER NOT NULL
);
CREATE TABLE idempotency (key TEXT PRIMARY KEY, cart_id TEXT NOT NULL, response TEXT NOT NULL);
CREATE TABLE refunds (refund_id TEXT PRIMARY KEY, order_id TEXT NOT NULL, amount_cents INTEGER NOT NULL);
"""


class Store:
    def __init__(self) -> None:
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self._counters: dict[str, int] = {}

    def next_id(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}_{self._counters[prefix]:04d}"

    # carts
    def create_cart(self) -> str:
        cart_id = self.next_id("cart")
        self.db.execute("INSERT INTO carts VALUES (?, NULL, 'open')", (cart_id,))
        return cart_id

    def get_cart(self, cart_id: str):
        return self.db.execute("SELECT * FROM carts WHERE cart_id = ?", (cart_id,)).fetchone()

    def cart_items(self, cart_id: str) -> list[tuple[str, int]]:
        rows = self.db.execute(
            "SELECT sku, quantity FROM cart_items WHERE cart_id = ? ORDER BY position", (cart_id,)
        )
        return [(r["sku"], r["quantity"]) for r in rows]

    def add_item(self, cart_id: str, sku: str, quantity: int) -> None:
        existing = self.db.execute(
            "SELECT quantity FROM cart_items WHERE cart_id = ? AND sku = ?", (cart_id, sku)
        ).fetchone()
        if existing:
            self.db.execute(
                "UPDATE cart_items SET quantity = ? WHERE cart_id = ? AND sku = ?",
                (existing["quantity"] + quantity, cart_id, sku),
            )
            return
        position = len(self.cart_items(cart_id))
        self.db.execute(
            "INSERT INTO cart_items VALUES (?, ?, ?, ?)", (cart_id, position, sku, quantity)
        )

    def set_coupon(self, cart_id: str, code: str) -> None:
        self.db.execute("UPDATE carts SET coupon_id = ? WHERE cart_id = ?", (code, cart_id))

    def close_cart(self, cart_id: str) -> None:
        self.db.execute("UPDATE carts SET status = 'checked_out' WHERE cart_id = ?", (cart_id,))

    # orders
    def save_order(self, order_id, cart_id, pricing: PricingResult, payment, lines) -> None:
        self.db.execute(
            "INSERT INTO orders VALUES (?, ?, ?, 'paid', ?, ?)",
            (order_id, cart_id, json.dumps(pricing.to_dict()), payment.payment_id, payment.captured_cents),
        )
        for position, line in enumerate(lines):
            self.db.execute(
                "INSERT INTO order_items VALUES (?, ?, ?, ?, ?)",
                (order_id, position, line.sku, line.quantity, line.unit_price_cents),
            )

    def get_order(self, order_id: str):
        return self.db.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()

    def order_pricing(self, order) -> PricingResult:
        return PricingResult.from_dict(json.loads(order["pricing_json"]))

    def order_lines(self, order_id: str) -> list[tuple[str, int, int]]:
        rows = self.db.execute(
            "SELECT sku, quantity, unit_price_cents FROM order_items WHERE order_id = ? ORDER BY position",
            (order_id,),
        )
        return [(r["sku"], r["quantity"], r["unit_price_cents"]) for r in rows]

    def save_refund(self, refund_id: str, order_id: str, amount_cents: int) -> None:
        self.db.execute("INSERT INTO refunds VALUES (?, ?, ?)", (refund_id, order_id, amount_cents))
        self.db.execute("UPDATE orders SET status = 'refunded' WHERE order_id = ?", (order_id,))

    # idempotency
    def get_idempotent(self, key: str):
        return self.db.execute("SELECT * FROM idempotency WHERE key = ?", (key,)).fetchone()

    def put_idempotent(self, key: str, cart_id: str, response: str) -> None:
        self.db.execute("INSERT INTO idempotency VALUES (?, ?, ?)", (key, cart_id, response))
