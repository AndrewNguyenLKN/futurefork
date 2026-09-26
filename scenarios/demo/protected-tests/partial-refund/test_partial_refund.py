"""F1 (hypothesis): partial refund allocation. Written strictly from the frozen public_interface."""

from __future__ import annotations

import pytest

from oracle_model import RefundModel
from pocketcart import catalog
from support import expect


# --- helpers -----------------------------------------------------------------------

def make_order(client, items: dict[str, int], coupon: str | None = None) -> dict:
    cart_id = expect(client.post("/carts"), 201)["cart_id"]
    for sku, quantity in items.items():
        expect(client.post(f"/carts/{cart_id}/items", {"sku": sku, "quantity": quantity}), 200)
    if coupon:
        expect(client.post(f"/carts/{cart_id}/coupon", {"code": coupon}), 200)
    return expect(client.checkout(cart_id), 201)


def refund(client, order_id: str, items: list[tuple[str, int]]):
    body = {"items": [{"sku": sku, "quantity": quantity} for sku, quantity in items]}
    return client.post(f"/orders/{order_id}/refunds", body)


def amounts(body: dict) -> dict[str, tuple[int, int]]:
    return {i["sku"]: (i["quantity"], i["amount_cents"]) for i in body["items"]}


def model_for(client, order: dict) -> RefundModel:
    eligible = {p["sku"]: p["coupon_eligible"] for p in client.get("/products").body["products"]}
    lines = [(i["sku"], i["quantity"], i["unit_price_cents"], eligible[i["sku"]]) for i in order["items"]]
    return RefundModel(lines, order["discount_cents"])


# --- regression guard --------------------------------------------------------------

@pytest.mark.guard
def test_existing_full_refund_remains_compatible(client):
    order = make_order(client, {"TSHIRT": 2, "GIFTCARD": 1}, "SAVE10")
    body = expect(client.post(f"/orders/{order['order_id']}/refund"), 201)
    assert body == {"refund_id": "ref_0001", "order_id": order["order_id"], "status": "refunded", "amount_cents": 8600}


# --- hand-derived literals -----------------------------------------------------------

def test_refund_one_discounted_item_returns_price_minus_its_share(client):
    # SAVE10 on 3250 eligible = 325; TSHIRT carries 200, MUG carries 125. Captured 2925.
    order = make_order(client, {"TSHIRT": 1, "MUG": 1}, "SAVE10")
    body = expect(refund(client, order["order_id"], [("TSHIRT", 1)]), 201)
    assert body["order_id"] == order["order_id"] and body["status"] == "refunded"
    assert body["refund_id"] == "ref_0001"
    assert amounts(body) == {"TSHIRT": (1, 1800)}
    assert body["amount_cents"] == 1800
    assert body["remaining_refundable_cents"] == 1125


def test_ineligible_line_carries_no_discount(client):
    order = make_order(client, {"TSHIRT": 1, "GIFTCARD": 1}, "SAVE10")  # D = 200, all on TSHIRT
    assert expect(refund(client, order["order_id"], [("GIFTCARD", 1)]), 201)["amount_cents"] == 5000
    assert expect(refund(client, order["order_id"], [("TSHIRT", 1)]), 201)["amount_cents"] == 1800


def test_orders_without_a_coupon_refund_full_unit_prices(client):
    order = make_order(client, {"HOODIE": 2, "MUG": 1})
    body = expect(refund(client, order["order_id"], [("HOODIE", 1)]), 201)
    assert body["amount_cents"] == 4999 and body["remaining_refundable_cents"] == 6249  # captured 11248


def test_remainder_cents_go_to_largest_remainders_then_earlier_lines(client):
    # SAVE25 on 3449 eligible: D = 862, floors 499/312/49 (sum 860). Remainders 2949/1412/2537:
    # the two leftover cents go to TSHIRT and STICKER, so shares are 500/312/50.
    order = make_order(client, {"TSHIRT": 1, "MUG": 1, "STICKER": 1}, "SAVE25")
    assert order["discount_cents"] == 862
    body = expect(refund(client, order["order_id"], [("TSHIRT", 1), ("MUG", 1), ("STICKER", 1)]), 201)
    assert amounts(body) == {"TSHIRT": (1, 1500), "MUG": (1, 938), "STICKER": (1, 149)}
    assert body["amount_cents"] == 2587 == order["payment"]["captured_cents"]
    assert body["remaining_refundable_cents"] == 0


def test_same_remainder_allocation_when_items_are_refunded_one_by_one(client):
    order = make_order(client, {"TSHIRT": 1, "MUG": 1, "STICKER": 1}, "SAVE25")
    got = [expect(refund(client, order["order_id"], [(sku, 1)]), 201)["amount_cents"] for sku in ("STICKER", "MUG", "TSHIRT")]
    assert got == [149, 938, 1500]


def test_units_of_one_line_use_cumulative_floor_split(client):
    # STICKER x3 with SAVE25: line 597, D = 149, unit shares 49, 50, 50.
    order = make_order(client, {"STICKER": 3}, "SAVE25")
    assert order["discount_cents"] == 149
    got = [expect(refund(client, order["order_id"], [("STICKER", 1)]), 201) for _ in range(3)]
    assert [g["amount_cents"] for g in got] == [150, 149, 149]
    assert [g["remaining_refundable_cents"] for g in got] == [298, 149, 0]


def test_unit_split_depends_on_units_already_refunded_not_on_operation_size(client):
    order = make_order(client, {"STICKER": 3}, "SAVE25")
    first = expect(refund(client, order["order_id"], [("STICKER", 2)]), 201)
    second = expect(refund(client, order["order_id"], [("STICKER", 1)]), 201)
    assert (first["amount_cents"], second["amount_cents"]) == (299, 149)


def test_full_refund_endpoint_refunds_only_what_remains(client):
    order = make_order(client, {"MUG": 2}, "SAVE10")  # D = 250, captured 2250, unit shares 125/125
    assert expect(refund(client, order["order_id"], [("MUG", 1)]), 201)["amount_cents"] == 1125
    rest = expect(client.post(f"/orders/{order['order_id']}/refund"), 201)
    assert (rest["refund_id"], rest["amount_cents"], rest["status"]) == ("ref_0002", 1125, "refunded")
    again = client.post(f"/orders/{order['order_id']}/refund")
    expect(again, 409, "already_refunded")


def test_refund_ids_share_one_sequence_across_both_endpoints(client):
    first = make_order(client, {"MUG": 1})
    second = make_order(client, {"MUG": 1})
    assert expect(refund(client, first["order_id"], [("MUG", 1)]), 201)["refund_id"] == "ref_0001"
    assert expect(client.post(f"/orders/{second['order_id']}/refund"), 201)["refund_id"] == "ref_0002"


def test_zero_total_order_refunds_zero_without_error(client):
    order = make_order(client, {"TSHIRT": 1, "MUG": 1}, "FULLRIDE")
    assert order["total_cents"] == 0
    body = expect(refund(client, order["order_id"], [("TSHIRT", 1)]), 201)
    assert body["amount_cents"] == 0 and body["remaining_refundable_cents"] == 0


def test_multi_item_operation_sums_line_amounts(client):
    order = make_order(client, {"TSHIRT": 1, "MUG": 1}, "SAVE10")
    body = expect(refund(client, order["order_id"], [("TSHIRT", 1), ("MUG", 1)]), 201)
    assert amounts(body) == {"TSHIRT": (1, 1800), "MUG": (1, 1125)}
    assert body["amount_cents"] == 2925 == order["payment"]["captured_cents"]


# --- historical pricing ----------------------------------------------------------------

def test_refund_uses_pricing_recorded_at_checkout_not_todays_coupon(client):
    order = make_order(client, {"TSHIRT": 1, "MUG": 1}, "SAVE10")
    # The coupon definition changes after checkout. Refunds must not notice.
    original = catalog.COUPONS["SAVE10"]
    catalog.COUPONS["SAVE10"] = catalog.Coupon("SAVE10", 50)
    try:
        body = expect(refund(client, order["order_id"], [("TSHIRT", 1)]), 201)
        assert body["amount_cents"] == 1800 and body["remaining_refundable_cents"] == 1125
        last = expect(refund(client, order["order_id"], [("MUG", 1)]), 201)
        assert last["amount_cents"] == 1125 and last["remaining_refundable_cents"] == 0
    finally:
        catalog.COUPONS["SAVE10"] = original


# --- invariants against the executable model ---------------------------------------------

CARTS = [
    ({"TSHIRT": 3, "MUG": 2, "STICKER": 5}, "SAVE25"),
    ({"HOODIE": 2, "GIFTCARD": 1, "STICKER": 7}, "SAVE10"),
    ({"STICKER": 9, "MUG": 1}, "SAVE25"),
    ({"TSHIRT": 2, "HOODIE": 1, "MUG": 3, "STICKER": 4}, "FULLRIDE"),
    ({"MUG": 4, "TSHIRT": 1}, None),
]
PLANS = {
    "one-unit-at-a-time": lambda lines: [[(s, 1)] for s, q in lines for _ in range(q)],
    "whole-lines-reverse": lambda lines: [[(s, q)] for s, q in reversed(lines)],
    "two-big-operations": lambda lines: [lines[: len(lines) // 2 or 1], lines[len(lines) // 2 or 1:]],
}


@pytest.mark.parametrize("plan", sorted(PLANS))
@pytest.mark.parametrize("items,coupon", CARTS)
def test_every_operation_matches_the_rules_and_totals_equal_captured(client, items, coupon, plan):
    order = make_order(client, items, coupon)
    model = model_for(client, order)
    lines = [(i["sku"], i["quantity"]) for i in order["items"]]
    captured = order["payment"]["captured_cents"]
    summed = 0
    for operation in PLANS[plan](lines):
        if not operation:
            continue
        expected = model.refund(operation)
        body = expect(refund(client, order["order_id"], operation), 201)
        assert {s: a for s, (_, a) in amounts(body).items()} == expected["items"]
        assert body["amount_cents"] == expected["amount_cents"] == sum(a for _, a in amounts(body).values())
        assert body["remaining_refundable_cents"] == expected["remaining_refundable_cents"]
        summed += body["amount_cents"]
        assert 0 <= summed <= captured
    assert summed == captured


def test_identical_orders_refund_identically(client):
    a = make_order(client, {"TSHIRT": 2, "MUG": 1, "STICKER": 3}, "SAVE25")
    b = make_order(client, {"TSHIRT": 2, "MUG": 1, "STICKER": 3}, "SAVE25")
    ops = [[("STICKER", 2)], [("TSHIRT", 1), ("MUG", 1)]]
    got_a = [expect(refund(client, a["order_id"], op), 201) for op in ops]
    got_b = [expect(refund(client, b["order_id"], op), 201) for op in ops]
    strip = lambda r: {k: v for k, v in r.items() if k not in ("refund_id", "order_id")}
    assert [strip(r) for r in got_a] == [strip(r) for r in got_b]


# --- errors ----------------------------------------------------------------------------------

def test_unknown_order_is_404(client):
    expect(refund(client, "order_9999", [("MUG", 1)]), 404, "order_not_found")


def test_invalid_refund_items_are_422(client):
    order = make_order(client, {"MUG": 2, "TSHIRT": 1})
    oid = order["order_id"]
    expect(client.post(f"/orders/{oid}/refunds", {"items": []}), 422, "invalid_refund_items")
    expect(refund(client, oid, [("HOODIE", 1)]), 422, "invalid_refund_items")       # sku not in order
    expect(refund(client, oid, [("MUG", 0)]), 422, "invalid_refund_items")
    expect(refund(client, oid, [("MUG", -1)]), 422, "invalid_refund_items")
    expect(refund(client, oid, [("MUG", 1), ("MUG", 1)]), 422, "invalid_refund_items")  # duplicate sku


def test_refund_beyond_remaining_units_is_409(client):
    order = make_order(client, {"MUG": 2}, "SAVE10")
    oid = order["order_id"]
    expect(refund(client, oid, [("MUG", 3)]), 409, "refund_exceeds_order")
    expect(refund(client, oid, [("MUG", 2)]), 201)
    expect(refund(client, oid, [("MUG", 1)]), 409, "refund_exceeds_order")
    expect(client.post(f"/orders/{oid}/refund"), 409, "already_refunded")


def test_item_endpoint_on_order_refunded_in_full_is_409(client):
    order = make_order(client, {"MUG": 1})
    expect(client.post(f"/orders/{order['order_id']}/refund"), 201)
    expect(refund(client, order["order_id"], [("MUG", 1)]), 409, "refund_exceeds_order")


def test_partial_refunds_of_one_line_cannot_exceed_its_quantity_across_operations(client):
    order = make_order(client, {"STICKER": 3}, "SAVE25")
    oid = order["order_id"]
    expect(refund(client, oid, [("STICKER", 2)]), 201)
    expect(refund(client, oid, [("STICKER", 2)]), 409, "refund_exceeds_order")
    assert expect(refund(client, oid, [("STICKER", 1)]), 201)["remaining_refundable_cents"] == 0
