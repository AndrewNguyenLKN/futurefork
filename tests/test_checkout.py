def test_checkout_records_subtotal_discount_total_and_coupon(client):
    order = client.order_with({"TSHIRT": 2, "GIFTCARD": 1}, "SAVE10")
    assert order == {
        "order_id": "order_0001",
        "cart_id": "cart_0001",
        "status": "paid",
        "items": [
            {"sku": "TSHIRT", "quantity": 2, "unit_price_cents": 2000, "line_total_cents": 4000},
            {"sku": "GIFTCARD", "quantity": 1, "unit_price_cents": 5000, "line_total_cents": 5000},
        ],
        "coupon_id": "SAVE10",
        "subtotal_cents": 9000,
        "discount_cents": 400,
        "total_cents": 8600,
        "payment": {"payment_id": "pay_0001", "captured_cents": 8600},
    }


def test_checkout_without_coupon(client):
    order = client.order_with({"MUG": 3})
    assert (order["coupon_id"], order["discount_cents"], order["total_cents"]) == (None, 0, 3750)
    assert order["payment"]["captured_cents"] == 3750


def test_zero_total_order_captures_zero(client):
    order = client.order_with({"MUG": 1}, "FULLRIDE")
    assert order["total_cents"] == 0 and order["payment"]["captured_cents"] == 0


def test_order_can_be_fetched_and_matches_checkout_response(client):
    order = client.order_with({"HOODIE": 1}, "SAVE25")
    assert client.get(f"/orders/{order['order_id']}").body == order


def test_order_keeps_price_paid_when_cart_is_read_again(client):
    order = client.order_with({"TSHIRT": 1}, "SAVE10")
    cart = client.get(f"/carts/{order['cart_id']}").body
    assert cart["total_cents"] == order["total_cents"]


def test_empty_cart_cannot_check_out(client):
    cart_id = client.post("/carts").body["cart_id"]
    response = client.checkout(cart_id)
    assert response.status == 422 and response.body["error"]["code"] == "empty_cart"


def test_checkout_input_errors(client):
    cart_id = client.cart_with({"MUG": 1})
    missing_key = client.post("/checkout", {"cart_id": cart_id})
    assert missing_key.status == 400 and missing_key.body["error"]["code"] == "missing_idempotency_key"
    assert client.post("/checkout", {}, headers={"Idempotency-Key": "k"}).status == 422
    unknown = client.checkout("cart_9999")
    assert unknown.status == 404 and unknown.body["error"]["code"] == "cart_not_found"
    assert client.get("/orders/order_9999").status == 404


def test_second_checkout_of_same_cart_with_new_key_conflicts(client):
    cart_id = client.cart_with({"MUG": 1})
    assert client.checkout(cart_id, "a").status == 201
    again = client.checkout(cart_id, "b")
    assert again.status == 409 and again.body["error"]["code"] == "cart_closed"
