import pytest


def test_create_cart_is_empty_and_open(client):
    cart_id = client.post("/carts").body["cart_id"]
    assert cart_id == "cart_0001"
    cart = client.get(f"/carts/{cart_id}").body
    assert cart == {
        "cart_id": "cart_0001", "status": "open", "items": [], "coupon_id": None,
        "subtotal_cents": 0, "discount_cents": 0, "total_cents": 0,
    }


def test_add_items_merges_same_sku_and_prices_lines(client):
    cart_id = client.cart_with({"TSHIRT": 2, "MUG": 1})
    client.post(f"/carts/{cart_id}/items", {"sku": "TSHIRT", "quantity": 1})
    cart = client.get(f"/carts/{cart_id}").body
    assert [(i["sku"], i["quantity"], i["line_total_cents"]) for i in cart["items"]] == [
        ("TSHIRT", 3, 6000), ("MUG", 1, 1250),
    ]
    assert cart["subtotal_cents"] == 7250 and cart["total_cents"] == 7250


@pytest.mark.parametrize("quantity", [0, -1, 100, "2", 1.5, True, None])
def test_invalid_quantity_is_rejected(client, quantity):
    cart_id = client.post("/carts").body["cart_id"]
    response = client.post(f"/carts/{cart_id}/items", {"sku": "MUG", "quantity": quantity})
    assert response.status == 422 and response.body["error"]["code"] == "invalid_quantity"


def test_merged_quantity_cannot_exceed_limit(client):
    cart_id = client.cart_with({"MUG": 60})
    response = client.post(f"/carts/{cart_id}/items", {"sku": "MUG", "quantity": 40})
    assert response.status == 422 and response.body["error"]["code"] == "invalid_quantity"


def test_unknown_sku_and_missing_cart(client):
    cart_id = client.post("/carts").body["cart_id"]
    assert client.post(f"/carts/{cart_id}/items", {"sku": "NOPE", "quantity": 1}).body["error"]["code"] == "unknown_sku"
    missing = client.post("/carts/cart_9999/items", {"sku": "MUG", "quantity": 1})
    assert missing.status == 404 and missing.body["error"]["code"] == "cart_not_found"
    assert client.get("/carts/cart_9999").status == 404


def test_unknown_coupon_is_rejected_and_cart_unchanged(client):
    cart_id = client.cart_with({"MUG": 1})
    response = client.post(f"/carts/{cart_id}/coupon", {"code": "BOGUS"})
    assert response.status == 422 and response.body["error"]["code"] == "unknown_coupon"
    assert client.get(f"/carts/{cart_id}").body["coupon_id"] is None


def test_checked_out_cart_is_closed_to_changes(client):
    cart_id = client.cart_with({"MUG": 1})
    client.checkout(cart_id)
    response = client.post(f"/carts/{cart_id}/items", {"sku": "MUG", "quantity": 1})
    assert response.status == 409 and response.body["error"]["code"] == "cart_closed"
    assert client.post(f"/carts/{cart_id}/coupon", {"code": "SAVE10"}).status == 409
    assert client.get(f"/carts/{cart_id}").body["status"] == "checked_out"
