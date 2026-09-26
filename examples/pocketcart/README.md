# PocketCart (seed application)

A synthetic checkout service used by FutureFork. All data is fictional; there is no network access, real payment, or personal data. Standard library only (tests need `pytest`).

Two candidates implement the **same current behavior** with different internal designs:

| | `candidates/coupled` | `candidates/modular` |
|---|---|---|
| Discount rule | `discounts.coupon_discount()` called directly from carts, checkout, and refunds | `pricing/` package: `DiscountPolicy` interface, `PricingService`, `PricingResult` |
| Persistence | `orders` row stores a scalar `discount_cents` plus `coupon_id` | `orders` row stores the whole `PricingResult` as `pricing_json` |
| Full refund | re-derives the refundable amount from stored lines and the coupon table | reads the total recorded at checkout |

Seven files are byte-identical in both (`wsgi.py`, `catalog.py`, `payments.py`, `validation.py`, `errors.py`, `__init__.py`, `__main__.py`); the designs differ only in `store.py`, `carts.py`, `checkout.py`, `refunds.py`, `service.py`, and the discount code. Neither contains code for any future scenario, and the equivalence tests assert that.

## API (current contract)

| Method and path | Result |
|---|---|
| `GET /products` | Product list with `coupon_eligible` |
| `POST /carts` | `201 {cart_id}` |
| `GET /carts/{id}` | Cart with `subtotal_cents`, `discount_cents`, `total_cents`, `coupon_id` |
| `POST /carts/{id}/items` `{sku, quantity 1..99}` | Cart; same sku merges |
| `POST /carts/{id}/coupon` `{code}` | Cart; replaces any earlier coupon |
| `POST /checkout` `{cart_id}` + `Idempotency-Key` header | `201` order; replay of the same key returns `200` with the original body |
| `GET /orders/{id}` | Order |
| `POST /orders/{id}/refund` | `201` full refund of the captured total; a second refund is `409` |

Coupons: `SAVE10` (10%), `SAVE25` (25%), `FULLRIDE` (100%). A percentage applies to coupon-eligible lines only, rounds half up to the cent, and never exceeds the subtotal. IDs are sequential (`cart_0001`, `order_0001`, `pay_0001`, `ref_0001`); responses are canonical JSON (sorted keys, no whitespace).

Run a candidate: `cd candidates/coupled && PYTHONPATH=src python -m pocketcart --port 8000`.

## Verification

```bash
# each candidate's own suite (identical files in both)
cd examples/pocketcart/candidates/coupled && ../../../../.venv/bin/python -m pytest -q
cd examples/pocketcart/candidates/modular && ../../../../.venv/bin/python -m pytest -q

# byte-identical tests + identical responses over WSGI and real HTTP + golden hash
.venv/bin/python examples/pocketcart/equivalence/check_equivalence.py
```

`equivalence/script.json` is a 64-request transcript (happy paths and error paths). `equivalence/golden-transcript.sha256` freezes its response hash so the later present-day refactor of `coupled` can be checked against today's behavior. That hash proves the two candidates agree with each other; the hand-computed expectations in `tests/` are what tie the behavior to the written contract.

## Git refs

`scripts/create_candidate_refs.sh` creates the local branches `coupled` and `modular` as parentless commits whose trees are exactly `candidates/coupled` and `candidates/modular` (Git plumbing; it does not touch the working tree, index, or HEAD, and refuses to overwrite). `python examples/pocketcart/equivalence/check_equivalence.py --refs .` verifies the refs instead of the directories. The refs are snapshots: if a candidate directory changes, delete the ref deliberately and recreate it.

## Provenance

This seed application, its tests, and the equivalence harness were written by Claude Code, not by IBM Bob. No Bob task is associated with them.
