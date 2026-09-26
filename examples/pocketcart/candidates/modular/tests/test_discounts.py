"""Percentage coupon behavior, observed through the cart quote."""

import pytest


def quote(client, items, coupon=None):
    body = client.get(f"/carts/{client.cart_with(items, coupon)}").body
    return body["subtotal_cents"], body["discount_cents"], body["total_cents"]


def test_percentage_coupon_applies_to_eligible_items_only(client):
    # 2 x TSHIRT (eligible) + GIFTCARD (not eligible): 10% of 4000.
    assert quote(client, {"TSHIRT": 2, "GIFTCARD": 1}, "SAVE10") == (9000, 400, 8600)


def test_no_coupon_means_no_discount(client):
    assert quote(client, {"TSHIRT": 1}) == (2000, 0, 2000)


def test_coupon_on_only_ineligible_items_gives_zero_discount(client):
    assert quote(client, {"GIFTCARD": 1}, "SAVE10") == (5000, 0, 5000)


@pytest.mark.parametrize(
    "items,coupon,discount",
    [
        ({"STICKER": 1}, "SAVE10", 20),    # 19.9 -> 20
        ({"STICKER": 1}, "SAVE25", 50),    # 49.75 -> 50
        ({"HOODIE": 1}, "SAVE10", 500),    # 499.9 -> 500
        ({"MUG": 1}, "SAVE25", 313),       # exactly 312.5 -> rounds half up
        ({"MUG": 2}, "SAVE10", 250),       # exact
    ],
)
def test_rounding_is_half_up_in_cents(client, items, coupon, discount):
    assert quote(client, items, coupon)[1] == discount


def test_discount_cannot_exceed_subtotal(client):
    subtotal, discount, total = quote(client, {"TSHIRT": 1, "MUG": 1}, "FULLRIDE")
    assert (subtotal, discount, total) == (3250, 3250, 0)
    # Ineligible items keep the discount below the subtotal.
    assert quote(client, {"TSHIRT": 1, "GIFTCARD": 1}, "FULLRIDE") == (7000, 2000, 5000)


def test_reapplying_a_coupon_replaces_the_previous_one(client):
    cart_id = client.cart_with({"TSHIRT": 1}, "SAVE10")
    body = client.post(f"/carts/{cart_id}/coupon", {"code": "SAVE25"}).body
    assert body["coupon_id"] == "SAVE25" and body["discount_cents"] == 500


def test_coupon_applies_after_items_are_added_later(client):
    cart_id = client.cart_with({"TSHIRT": 1}, "SAVE10")
    client.post(f"/carts/{cart_id}/items", {"sku": "MUG", "quantity": 2})
    assert client.get(f"/carts/{cart_id}").body["discount_cents"] == 450
