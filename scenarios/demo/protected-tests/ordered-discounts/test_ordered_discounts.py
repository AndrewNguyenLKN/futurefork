"""F3 (hypothesis): ordered discount composition. Written strictly from the frozen public_interface.

The interface does not say whether a component worth 0 cents is listed, so comparisons drop
zero-amount components rather than over-constraining implementations.
"""

from __future__ import annotations

import pytest

from oracle_model import COUPON_PERCENT, ORGANIZATIONS, compose
from support import expect, field


# --- helpers -----------------------------------------------------------------------

def new_cart(client, items, organization_id=None, coupon=None) -> str:
    body = {"organization_id": organization_id} if organization_id else None
    cart_id = expect(client.post("/carts", body), 201)["cart_id"]
    for sku, quantity in items.items():
        expect(client.post(f"/carts/{cart_id}/items", {"sku": sku, "quantity": quantity}), 200)
    if coupon:
        expect(client.post(f"/carts/{cart_id}/coupon", {"code": coupon}), 200)
    return cart_id


def amounts_in_cart(client, items) -> tuple[int, int]:
    products = {p["sku"]: p for p in client.get("/products").body["products"]}
    line = lambda sku: items[sku] * products[sku]["unit_price_cents"]
    return sum(line(s) for s in items if products[s]["coupon_eligible"]), sum(line(s) for s in items)


def components(body: dict) -> list[dict]:
    assert "discounts" in body, f"'discounts' missing from {sorted(body)}"
    return [c for c in body["discounts"] if c["amount_cents"] != 0]


def check_pricing(body: dict, expected: list[dict], subtotal: int) -> None:
    assert [(c["source"], c["id"], c["amount_cents"]) for c in components(body)] == \
        [(c["source"], c["id"], c["amount_cents"]) for c in expected if c["amount_cents"]]
    assert sum(c["amount_cents"] for c in body["discounts"]) == body["discount_cents"]
    assert body["discount_cents"] == sum(c["amount_cents"] for c in expected) <= subtotal
    assert body["subtotal_cents"] == subtotal
    assert body["total_cents"] == subtotal - body["discount_cents"]


ITEM_SETS = [
    {"TSHIRT": 2, "GIFTCARD": 1}, {"MUG": 1}, {"STICKER": 1}, {"TSHIRT": 1, "MUG": 1},
    {"HOODIE": 99}, {"GIFTCARD": 1},
]
COUPONS = [None, "SAVE10", "SAVE25", "FULLRIDE"]
ORGS = [None, *sorted(ORGANIZATIONS)]


# --- compatibility -----------------------------------------------------------------------

@pytest.mark.guard
def test_existing_single_coupon_keys_and_values_are_unchanged(client):
    cart_id = new_cart(client, {"TSHIRT": 2, "GIFTCARD": 1}, coupon="SAVE10")
    cart = client.get(f"/carts/{cart_id}").body
    for key, value in {
        "cart_id": cart_id, "status": "open", "coupon_id": "SAVE10", "subtotal_cents": 9000,
        "discount_cents": 400, "total_cents": 8600,
    }.items():
        assert cart[key] == value
    order = expect(client.checkout(cart_id), 201)
    assert (order["coupon_id"], order["discount_cents"], order["total_cents"]) == ("SAVE10", 400, 8600)
    assert order["payment"]["captured_cents"] == 8600
    assert expect(client.post(f"/orders/{order['order_id']}/refund"), 201)["amount_cents"] == 8600


def test_consumer_carts_list_their_coupon_as_the_only_component(client):
    cart = client.get(f"/carts/{new_cart(client, {'TSHIRT': 2, 'GIFTCARD': 1}, coupon='SAVE10')}").body
    assert field(cart, "discounts") == [{"source": "coupon", "id": "SAVE10", "amount_cents": 400}]
    assert cart["discount_cents"] == 400 and cart["total_cents"] == 8600


def test_carts_without_any_discount_list_no_components(client):
    assert field(client.get(f"/carts/{new_cart(client, {'MUG': 1})}").body, "discounts") == []
    assert client.get(f"/carts/{new_cart(client, {'GIFTCARD': 1}, coupon='SAVE10')}").body["discount_cents"] == 0


# --- hand-derived literals ------------------------------------------------------------------

def test_organization_first_then_coupon(client):
    # acme: 20% of 4000 = 800; then SAVE10 on the remaining 3200 = 320.
    body = client.get(f"/carts/{new_cart(client, {'TSHIRT': 2, 'GIFTCARD': 1}, 'org-acme', 'SAVE10')}").body
    assert components(body) == [
        {"source": "organization", "id": "org-acme", "amount_cents": 800},
        {"source": "coupon", "id": "SAVE10", "amount_cents": 320},
    ]
    assert (body["discount_cents"], body["total_cents"], body["coupon_id"]) == (1120, 7880, "SAVE10")
    assert field(body, "organization_id") == "org-acme"


def test_coupon_first_then_organization(client):
    # globex: SAVE10 = 400 of 4000; then 15% of the remaining 3600 = 540.
    body = client.get(f"/carts/{new_cart(client, {'TSHIRT': 2, 'GIFTCARD': 1}, 'org-globex', 'SAVE10')}").body
    assert components(body) == [
        {"source": "coupon", "id": "SAVE10", "amount_cents": 400},
        {"source": "organization", "id": "org-globex", "amount_cents": 540},
    ]
    assert (body["discount_cents"], body["total_cents"]) == (940, 8060)


def test_organization_discount_alone_is_recorded_as_a_single_component(client):
    body = client.get(f"/carts/{new_cart(client, {'TSHIRT': 2}, 'org-acme')}").body
    assert components(body) == [{"source": "organization", "id": "org-acme", "amount_cents": 800}]
    assert body["coupon_id"] is None


def test_cap_applies_to_the_combined_result_in_application_order(client):
    # initech cap 500. TSHIRT x2: organization wants 1200 and consumes the whole cap.
    first = client.get(f"/carts/{new_cart(client, {'TSHIRT': 2}, 'org-initech', 'SAVE10')}").body
    assert components(first) == [{"source": "organization", "id": "org-initech", "amount_cents": 500}]
    assert (first["discount_cents"], first["total_cents"]) == (500, 3500)
    # MUG x1: organization 375 leaves 125 of cap; SAVE25 wants 219 and is truncated to 125.
    second = client.get(f"/carts/{new_cart(client, {'MUG': 1}, 'org-initech', 'SAVE25')}").body
    assert components(second) == [
        {"source": "organization", "id": "org-initech", "amount_cents": 375},
        {"source": "coupon", "id": "SAVE25", "amount_cents": 125},
    ]
    assert (second["discount_cents"], second["total_cents"]) == (500, 750)


def test_cap_is_consumed_by_whichever_component_applies_first(client):
    big = {"HOODIE": 99}  # subtotal 494901, all eligible
    coupon_first = client.get(f"/carts/{new_cart(client, big, 'org-globex', 'FULLRIDE')}").body
    assert components(coupon_first) == [{"source": "coupon", "id": "FULLRIDE", "amount_cents": 3000}]
    org_first = client.get(f"/carts/{new_cart(client, big, 'org-acme', 'FULLRIDE')}").body
    assert components(org_first) == [{"source": "organization", "id": "org-acme", "amount_cents": 3000}]
    assert org_first["total_cents"] == coupon_first["total_cents"] == 494901 - 3000


def test_combined_discount_never_exceeds_the_subtotal(client):
    # acme: 20% of 2000 = 400, then FULLRIDE takes the remaining 1600: exactly the subtotal.
    body = client.get(f"/carts/{new_cart(client, {'TSHIRT': 1}, 'org-acme', 'FULLRIDE')}").body
    assert (body["discount_cents"], body["total_cents"]) == (2000, 0)
    assert sum(c["amount_cents"] for c in field(body, "discounts")) == 2000


# --- matrix against the executable model ----------------------------------------------------------

@pytest.mark.parametrize("coupon", COUPONS)
@pytest.mark.parametrize("organization_id", ORGS)
@pytest.mark.parametrize("items", ITEM_SETS)
def test_cart_matches_the_composition_rules(client, items, organization_id, coupon):
    eligible, subtotal = amounts_in_cart(client, items)
    expected = compose(eligible, subtotal, organization_id, coupon)
    body = expect(client.get(f"/carts/{new_cart(client, items, organization_id, coupon)}"), 200)
    check_pricing(body, expected, subtotal)
    if organization_id:
        assert field(body, "organization_id") == organization_id


@pytest.mark.parametrize("coupon", ["SAVE10", "FULLRIDE"])
@pytest.mark.parametrize("organization_id", ORGS)
def test_order_records_every_component_and_matches_the_cart(client, organization_id, coupon):
    items = {"TSHIRT": 2, "MUG": 1, "GIFTCARD": 1}
    eligible, subtotal = amounts_in_cart(client, items)
    expected = compose(eligible, subtotal, organization_id, coupon)
    cart_id = new_cart(client, items, organization_id, coupon)
    order = expect(client.checkout(cart_id), 201)
    check_pricing(order, expected, subtotal)
    assert order["payment"]["captured_cents"] == order["total_cents"]
    fetched = expect(client.get(f"/orders/{order['order_id']}"), 200)
    assert components(fetched) == components(order) and fetched["discount_cents"] == order["discount_cents"]
    if organization_id:
        assert field(order, "organization_id") == organization_id
    refund = expect(client.post(f"/orders/{order['order_id']}/refund"), 201)
    assert refund["amount_cents"] == order["payment"]["captured_cents"]


def test_reapplying_a_coupon_replaces_the_previous_component(client):
    cart_id = new_cart(client, {"TSHIRT": 2}, "org-acme", "SAVE10")
    body = expect(client.post(f"/carts/{cart_id}/coupon", {"code": "SAVE25"}), 200)
    assert [(c["source"], c["id"]) for c in components(body)] == [("organization", "org-acme"), ("coupon", "SAVE25")]
    assert body["discount_cents"] == 800 + (3200 * 25 + 50) // 100


def test_unknown_organization_fails_safely_without_creating_a_cart(client):
    expect(client.post("/carts", {"organization_id": "org-unknown"}), 422, "unknown_organization")
    expect(client.get("/carts/cart_0001"), 404, "cart_not_found")
