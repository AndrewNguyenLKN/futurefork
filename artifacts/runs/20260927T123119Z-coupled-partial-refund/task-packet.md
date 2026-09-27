# FutureFork task packet — partial-refund

You are implementing one hypothetical future requirement in an isolated FutureFork experiment.

- Candidate: `coupled`
- Scenario: `partial-refund`
- Starting commit: `11f9d4e8559ec56fc818b9b9e72c2150e9560931`
- Workspace: the currently opened isolated Git worktree only
- Label: hypothesis, not a prediction

## Requirement

Refund selected order items. The refunded discount must be allocated deterministically across items, and the sum of item refunds must equal the order refund without exceeding the captured amount.

## Public acceptance criteria

1. Existing full refunds remain compatible.
2. Refunding one discounted item returns its price minus its allocated share of the order discount.
3. Refunding items across several operations never refunds more than the captured amount, and refunding every unit refunds exactly the captured amount.
4. Rounding is deterministic and follows the stated allocation rule.
5. Refund amounts come from the pricing recorded at checkout; later changes to a coupon definition do not change them.

## Public interface

- `POST /orders/{order_id}/refunds` — Refund selected units of an order.

  Request:
  ```json
  {
    "items": "[{sku: string, quantity: integer >= 1}]"
  }
  ```

  Response:
  ```json
  {
    "body": "{refund_id, order_id, status: 'refunded', items: [{sku, quantity, amount_cents}], amount_cents, remaining_refundable_cents}",
    "status": 201
  }
  ```

  Errors:
  ```json
  {
    "404": "order_not_found",
    "409": "refund_exceeds_order (quantity greater than units still refundable for that sku)",
    "422": "invalid_refund_items (empty list, sku not in order, quantity < 1)"
  }
  ```

- `POST /orders/{order_id}/refund` — Existing full refund. Now refunds all units not yet refunded; response shape unchanged.

### Rules

- Refund ids share one sequence, ref_0001, ref_0002, and so on, across both refund endpoints.
- Only order lines whose product was coupon-eligible at checkout carry an allocated discount.
- Let D be the order discount_cents and W the sum of line_total_cents over discounted lines. Line i receives floor(D * w_i / W) cents. The remaining cents are given one each to lines by descending (D * w_i mod W), ties broken by ascending line position (order in which the sku was first added to the cart).
- Within a line with quantity q and allocated discount L, refunding units j+1..j+n (j units already refunded) carries a discount of floor(L*(j+n)/q) - floor(L*j/q).
- Amount for n units of a line is n * unit_price_cents minus that discount. The sum over all q units equals line_total_cents minus L.
- An operation with several items sums per-line amounts; the same sku may not appear twice in one request (422 invalid_refund_items).
- Refund amounts must not depend on coupon definitions as they are at refund time.
- Requests for a fully refunded order return 409 already_refunded on the full-refund endpoint and 409 refund_exceeds_order on the item endpoint.
- Behavior of every endpoint that existed before this change is otherwise unchanged.

## Execution contract

- Editable paths: `src/**`, `tests/**`
- Do not modify `pyproject.toml`, Git metadata, task metadata, or anything outside this workspace.
- Do not access parent directories, other worktrees, the FutureFork repository, external data, or the network.
- Allowed commands: `python -m pytest`, `git status`, `git diff`
- Limits: 600 wall-clock seconds, at most 4 implementation attempts, at most 1000000 output bytes.

Implement the smallest coherent solution. Preserve all current behavior. Stop when the public
tests pass or the attempt limit is reached. In the final response, report assumptions, changed
files, tests run, and any unresolved issue. Do not claim external acceptance results.
