# FutureFork manual task packet — P0.3

You are implementing one hypothetical future requirement in an isolated FutureFork experiment.

- Candidate label: `A`
- Scenario: `partial-refund`
- Starting commit: `f9e3ecda1e4a8452678578226b2553a6ebddf536`
- Workspace: the currently opened isolated Git worktree only
- Label: hypothesis, not a prediction

## Requirement

Refund selected order items. The refunded discount must be allocated deterministically across items, and the sum of item refunds must equal the order refund without exceeding the captured amount.

## Public acceptance criteria

1. Existing full refunds remain compatible.
2. Refunding one discounted item returns its price minus its allocated share of the order discount.
3. Refunding items across several operations never refunds more than the captured amount, and refunding every unit refunds exactly the captured amount.
4. Rounding is deterministic and follows the stated allocation rule.
5. Refund amounts come from pricing recorded at checkout; later changes to a coupon definition do not change them.

## Public interface

Add `POST /orders/{order_id}/refunds`.

Request body:

```json
{"items": [{"sku": "string", "quantity": 1}]}
```

Successful response: HTTP `201` with:

```json
{
  "refund_id": "ref_0001",
  "order_id": "ord_0001",
  "status": "refunded",
  "items": [{"sku": "sku", "quantity": 1, "amount_cents": 0}],
  "amount_cents": 0,
  "remaining_refundable_cents": 0
}
```

Errors:

- `404 order_not_found`
- `422 invalid_refund_items` for an empty list, an SKU not in the order, or quantity below 1
- `409 refund_exceeds_order` when quantity exceeds the units still refundable for that SKU

The existing `POST /orders/{order_id}/refund` endpoint remains available. It now refunds all units not already refunded, and its response shape remains unchanged.

## Frozen rules

1. Refund IDs use one sequence (`ref_0001`, `ref_0002`, ...) across both refund endpoints.
2. Only order lines whose product was coupon-eligible at checkout carry an allocated discount.
3. Let `D` be the order `discount_cents` and `W` the sum of `line_total_cents` over discounted lines. Line `i` receives `floor(D * w_i / W)` cents. Give remaining cents one each to lines by descending `(D * w_i mod W)`, breaking ties by ascending line position (the order in which the SKU was first added to the cart).
4. Within a line with quantity `q` and allocated discount `L`, refunding units `j+1..j+n`, where `j` units were already refunded, carries discount `floor(L*(j+n)/q) - floor(L*j/q)`.
5. The amount for `n` units of a line is `n * unit_price_cents` minus that discount. Across all `q` units, the total equals `line_total_cents - L`.
6. An operation with several items sums the per-line amounts. The same SKU may not appear twice in one request; return `422 invalid_refund_items`.
7. Refund amounts must not depend on coupon definitions at refund time.
8. A fully refunded order returns `409 already_refunded` on the full-refund endpoint and `409 refund_exceeds_order` on the item endpoint.
9. All other existing endpoint behavior remains unchanged.

## Execution contract

- Editable paths: `src/**`, `tests/**`
- Do not modify `pyproject.toml`, Git metadata, task metadata, or anything outside this workspace.
- Do not access parent directories, other worktrees, the FutureFork repository, external data, or the network.
- Allowed commands:
  - `python -m pytest -q`
  - `git status`
  - `git diff`
- Limits: 600 wall-clock seconds, at most 4 implementation attempts, at most 1,000,000 output bytes.

Inspect the current application, implement the smallest coherent solution, and add development tests where useful. Preserve all current behavior. Stop when the public tests pass or the attempt limit is reached. In the final response, report assumptions, changed files, tests run, and any unresolved issue. Do not claim external acceptance results.
