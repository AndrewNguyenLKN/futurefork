"""F2 (hypothesis): organization-specific pricing. Written strictly from the frozen public_interface."""

from __future__ import annotations

import pytest

from oracle_model import ORGANIZATIONS, organization_discount
from support import expect, field


# --- helpers -----------------------------------------------------------------------

def new_cart(client, items: dict[str, int], organization_id: str | None = None, coupon: str | None = None):
    body = {"organization_id": organization_id} if organization_id else None
    cart_id = expect(client.post("/carts", body), 201)["cart_id"]
    for sku, quantity in items.items():
        expect(client.post(f"/carts/{cart_id}/items", {"sku": sku, "quantity": quantity}), 200)
    if coupon:
        expect(client.post(f"/carts/{cart_id}/coupon", {"code": coupon}), 200)
    return cart_id


def eligible_and_subtotal(client, items: dict[str, int]) -> tuple[int, int]:
    products = {p["sku"]: p for p in client.get("/products").body["products"]}
    line = lambda sku: items[sku] * products[sku]["unit_price_cents"]
    return sum(line(s) for s in items if products[s]["coupon_eligible"]), sum(line(s) for s in items)


CONSUMER_CART = {
    "cart_id": "cart_0001", "status": "open", "coupon_id": "SAVE10",
    "items": [
        {"sku": "TSHIRT", "quantity": 2, "unit_price_cents": 2000, "line_total_cents": 4000},
        {"sku": "GIFTCARD", "quantity": 1, "unit_price_cents": 5000, "line_total_cents": 5000},
    ],
    "subtotal_cents": 9000, "discount_cents": 400, "total_cents": 8600,
}


# --- consumer path must not change ---------------------------------------------------------

@pytest.mark.guard
def test_consumer_cart_order_and_refund_json_are_exactly_as_before(client):
    cart_id = new_cart(client, {"TSHIRT": 2, "GIFTCARD": 1}, coupon="SAVE10")
    assert client.get(f"/carts/{cart_id}").body == CONSUMER_CART
    order = expect(client.checkout(cart_id), 201)
    assert set(order) == {"order_id", "cart_id", "status", "items", "coupon_id", "subtotal_cents",
                          "discount_cents", "total_cents", "payment"}
    assert client.get(f"/orders/{order['order_id']}").body == order
    assert expect(client.post(f"/orders/{order['order_id']}/refund"), 201) == {
        "refund_id": "ref_0001", "order_id": order["order_id"], "status": "refunded", "amount_cents": 8600,
    }


@pytest.mark.guard
def test_consumer_cart_creation_response_is_unchanged(client):
    assert expect(client.post("/carts"), 201) == {"cart_id": "cart_0001"}


@pytest.mark.guard
def test_consumer_behavior_is_unaffected_by_organization_traffic(client):
    client.post("/carts", {"organization_id": "org-acme"})
    client.post("/carts", {"organization_id": "org-globex"})
    cart_id = new_cart(client, {"TSHIRT": 2, "GIFTCARD": 1}, coupon="SAVE10")
    body = client.get(f"/carts/{cart_id}").body
    assert {k: body[k] for k in CONSUMER_CART if k != "cart_id"} == {k: v for k, v in CONSUMER_CART.items() if k != "cart_id"}
    assert set(body) == set(CONSUMER_CART)


# --- organization carts ------------------------------------------------------------------

@pytest.mark.parametrize("organization_id", sorted(ORGANIZATIONS))
def test_organization_cart_reports_organization_and_policy(client, organization_id):
    cart_id = new_cart(client, {"MUG": 1}, organization_id)
    body = expect(client.get(f"/carts/{cart_id}"), 200)
    assert field(body, "organization_id") == organization_id
    assert field(body, "policy_id") == ORGANIZATIONS[organization_id][0]
    assert body["coupon_id"] is None


@pytest.mark.parametrize("organization_id", sorted(ORGANIZATIONS))
@pytest.mark.parametrize(
    "items",
    [{"TSHIRT": 2, "GIFTCARD": 1}, {"MUG": 1}, {"STICKER": 1}, {"HOODIE": 2}, {"GIFTCARD": 1},
     {"TSHIRT": 1, "MUG": 1, "STICKER": 1}, {"HOODIE": 99}],
)
def test_organization_discount_follows_its_policy(client, organization_id, items):
    eligible, subtotal = eligible_and_subtotal(client, items)
    expected = organization_discount(organization_id, eligible, subtotal)
    body = expect(client.get(f"/carts/{new_cart(client, items, organization_id)}"), 200)
    assert field(body, "policy_id") == ORGANIZATIONS[organization_id][0]
    assert body["discount_cents"] == expected
    assert body["subtotal_cents"] == subtotal and body["total_cents"] == subtotal - expected


def test_organization_discount_literals(client):
    # acme 20%: 4000 eligible -> 800 (cap 1500 not reached).
    acme = client.get(f"/carts/{new_cart(client, {'TSHIRT': 2, 'GIFTCARD': 1}, 'org-acme')}").body
    assert (acme["discount_cents"], acme["total_cents"]) == (800, 8200)
    # globex 30% of 2000 = 600, capped at 500.
    globex = client.get(f"/carts/{new_cart(client, {'TSHIRT': 1}, 'org-globex')}").body
    assert (globex["discount_cents"], globex["total_cents"]) == (500, 1500)
    # acme on 9998 eligible: 20% = 2000, capped at 1500.
    capped = client.get(f"/carts/{new_cart(client, {'HOODIE': 2}, 'org-acme')}").body
    assert capped["discount_cents"] == 1500
    # half-up rounding: 20% of 199 = 39.8 -> 40.
    rounded = client.get(f"/carts/{new_cart(client, {'STICKER': 1}, 'org-acme')}").body
    assert rounded["discount_cents"] == 40


def test_two_organizations_apply_different_policies_to_the_same_cart(client):
    items = {"TSHIRT": 1}
    acme = client.get(f"/carts/{new_cart(client, items, 'org-acme')}").body
    globex = client.get(f"/carts/{new_cart(client, items, 'org-globex')}").body
    assert (acme["discount_cents"], field(acme, "policy_id")) == (400, "acme-standard")
    assert (globex["discount_cents"], field(globex, "policy_id")) == (500, "globex-volume")


def test_discount_is_recalculated_as_items_are_added(client):
    cart_id = new_cart(client, {"MUG": 1}, "org-acme")
    expect(client.post(f"/carts/{cart_id}/items", {"sku": "TSHIRT", "quantity": 1}), 200)
    assert client.get(f"/carts/{cart_id}").body["discount_cents"] == 650  # 20% of 3250


# --- orders --------------------------------------------------------------------------------

@pytest.mark.parametrize("organization_id", sorted(ORGANIZATIONS))
def test_order_records_organization_policy_and_pricing(client, organization_id):
    items = {"TSHIRT": 2, "GIFTCARD": 1}
    eligible, subtotal = eligible_and_subtotal(client, items)
    discount = organization_discount(organization_id, eligible, subtotal)
    order = expect(client.checkout(new_cart(client, items, organization_id)), 201)
    assert field(order, "organization_id") == organization_id
    assert field(order, "policy_id") == ORGANIZATIONS[organization_id][0]
    assert (order["subtotal_cents"], order["discount_cents"], order["total_cents"]) == (subtotal, discount, subtotal - discount)
    assert order["payment"]["captured_cents"] == subtotal - discount
    assert order["coupon_id"] is None
    fetched = expect(client.get(f"/orders/{order['order_id']}"), 200)
    assert field(fetched, "organization_id") == organization_id and field(fetched, "policy_id") == field(order, "policy_id")


def test_organization_order_full_refund_returns_captured_total(client):
    order = expect(client.checkout(new_cart(client, {"TSHIRT": 2, "GIFTCARD": 1}, "org-acme")), 201)
    body = expect(client.post(f"/orders/{order['order_id']}/refund"), 201)
    assert body["amount_cents"] == order["payment"]["captured_cents"] == 8200
    expect(client.post(f"/orders/{order['order_id']}/refund"), 409, "already_refunded")


def test_organization_checkout_is_idempotent(client):
    cart_id = new_cart(client, {"MUG": 2}, "org-globex")
    first = client.post("/checkout", {"cart_id": cart_id}, {"Idempotency-Key": "org-key"})
    replay = client.post("/checkout", {"cart_id": cart_id}, {"Idempotency-Key": "org-key"})
    assert (first.status, replay.status) == (201, 200)
    assert replay.raw == first.raw
    assert field(first.body, "organization_id") == "org-globex"
    assert expect(client.checkout(new_cart(client, {"MUG": 1})), 201)["payment"]["payment_id"] == "pay_0002"


# --- coupons and unknown organizations ---------------------------------------------------------

def test_coupon_on_organization_cart_is_rejected_and_cart_unchanged(client):
    cart_id = new_cart(client, {"TSHIRT": 1}, "org-acme")
    before = client.get(f"/carts/{cart_id}").body
    expect(client.post(f"/carts/{cart_id}/coupon", {"code": "SAVE10"}), 422, "coupon_not_allowed_for_organization")
    assert client.get(f"/carts/{cart_id}").body == before
    assert before["coupon_id"] is None and before["discount_cents"] == 400


def test_unknown_organization_fails_safely_without_creating_a_cart(client):
    expect(client.post("/carts", {"organization_id": "org-unknown"}), 422, "unknown_organization")
    expect(client.get("/carts/cart_0001"), 404, "cart_not_found")
    assert expect(client.post("/carts"), 201)["cart_id"] == "cart_0001"
