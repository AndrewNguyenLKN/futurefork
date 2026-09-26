def test_replayed_checkout_returns_same_order_without_a_second_capture(client):
    cart_id = client.cart_with({"TSHIRT": 1}, "SAVE10")
    first = client.checkout(cart_id, "same-key")
    replay = client.checkout(cart_id, "same-key")
    assert (first.status, replay.status) == (201, 200)
    assert replay.raw == first.raw
    # The replay did not create an order or payment: the next ones are numbered 2.
    second = client.order_with({"MUG": 1}, key="other-key")
    assert second["order_id"] == "order_0002"
    assert second["payment"]["payment_id"] == "pay_0002"


def test_reusing_a_key_for_a_different_cart_is_rejected(client):
    first_cart = client.cart_with({"MUG": 1})
    second_cart = client.cart_with({"MUG": 2})
    assert client.checkout(first_cart, "k").status == 201
    response = client.checkout(second_cart, "k")
    assert response.status == 409 and response.body["error"]["code"] == "idempotency_key_reuse"
    assert client.get(f"/carts/{second_cart}").body["status"] == "open"


def test_replay_returns_original_response_even_after_refund(client):
    cart_id = client.cart_with({"MUG": 1})
    first = client.checkout(cart_id, "k")
    client.post(f"/orders/{first.body['order_id']}/refund")
    replay = client.checkout(cart_id, "k")
    assert replay.status == 200 and replay.raw == first.raw
    assert replay.body["status"] == "paid"
