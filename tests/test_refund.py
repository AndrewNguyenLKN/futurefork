def test_full_refund_returns_captured_total(client):
    order = client.order_with({"TSHIRT": 2, "GIFTCARD": 1}, "SAVE10")
    response = client.post(f"/orders/{order['order_id']}/refund")
    assert response.status == 201
    assert response.body == {
        "refund_id": "ref_0001", "order_id": "order_0001", "status": "refunded", "amount_cents": 8600,
    }
    assert response.body["amount_cents"] == order["payment"]["captured_cents"]


def test_full_refund_without_coupon(client):
    order = client.order_with({"HOODIE": 1, "MUG": 1})
    assert client.post(f"/orders/{order['order_id']}/refund").body["amount_cents"] == 6249


def test_full_refund_of_zero_total_order(client):
    order = client.order_with({"MUG": 1}, "FULLRIDE")
    assert client.post(f"/orders/{order['order_id']}/refund").body["amount_cents"] == 0


def test_refund_marks_order_refunded(client):
    order = client.order_with({"MUG": 1})
    client.post(f"/orders/{order['order_id']}/refund")
    assert client.get(f"/orders/{order['order_id']}").body["status"] == "refunded"


def test_order_cannot_be_refunded_twice(client):
    order = client.order_with({"MUG": 1})
    assert client.post(f"/orders/{order['order_id']}/refund").status == 201
    again = client.post(f"/orders/{order['order_id']}/refund")
    assert again.status == 409 and again.body["error"]["code"] == "already_refunded"


def test_refund_of_unknown_order_is_404(client):
    response = client.post("/orders/order_9999/refund")
    assert response.status == 404 and response.body["error"]["code"] == "order_not_found"


def test_refund_ids_are_sequential(client):
    ids = [
        client.post(f"/orders/{client.order_with({'MUG': 1}, key=f'k{i}')['order_id']}/refund").body["refund_id"]
        for i in range(2)
    ]
    assert ids == ["ref_0001", "ref_0002"]
