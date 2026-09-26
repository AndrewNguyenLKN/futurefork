"""Wiring between the HTTP layer and the domain modules."""

from __future__ import annotations

from . import carts, checkout, refunds
from .payments import FakeGateway
from .store import Store


class PocketCartApi:
    def __init__(self) -> None:
        self.store = Store()
        self.gateway = FakeGateway()

    def create_cart(self) -> dict:
        return carts.create_cart(self.store)

    def get_cart(self, cart_id: str) -> dict:
        return carts.cart_view(self.store, cart_id)

    def add_item(self, cart_id: str, sku: str, quantity: int) -> dict:
        return carts.add_item(self.store, cart_id, sku, quantity)

    def apply_coupon(self, cart_id: str, code: str) -> dict:
        return carts.apply_coupon(self.store, cart_id, code)

    def checkout(self, cart_id: str, key: str) -> tuple[dict, bool]:
        return checkout.checkout(self.store, self.gateway, cart_id, key)

    def get_order(self, order_id: str) -> dict:
        return checkout.order_view(self.store, order_id)

    def refund_order(self, order_id: str) -> dict:
        return refunds.refund_order(self.store, order_id)
