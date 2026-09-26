def test_products_lists_synthetic_catalog(client):
    response = client.get("/products")
    assert response.status == 200
    skus = [p["sku"] for p in response.body["products"]]
    assert skus == ["TSHIRT", "MUG", "HOODIE", "STICKER", "GIFTCARD"]
    giftcard = response.body["products"][-1]
    assert giftcard["unit_price_cents"] == 5000 and giftcard["coupon_eligible"] is False


def test_unknown_route_is_404(client):
    response = client.get("/nope")
    assert response.status == 404
    assert response.body["error"]["code"] == "not_found"


def test_wrong_method_is_405(client):
    assert client.get("/checkout").status == 405
    assert client.request("POST", "/products").status == 405


def test_invalid_json_is_400(client):
    cart_id = client.post("/carts").body["cart_id"]
    bad = client.post(f"/carts/{cart_id}/items", raw_body=b"{not json")
    assert bad.status == 400 and bad.body["error"]["code"] == "invalid_json"
    not_object = client.post(f"/carts/{cart_id}/items", raw_body=b"[1]")
    assert not_object.status == 400


def test_responses_are_deterministic_bytes(client):
    first = client.get("/products").raw
    assert first == client.get("/products").raw
    assert first.startswith(b'{"products":[{"coupon_eligible":true,')
