# Canonical demo story

## Demo promise

In under three minutes, show that two implementations can be equally correct today but produce materially different evidence when IBM Bob tries to evolve them under the same future requirements.

## Seed application: PocketCart

PocketCart is a synthetic checkout service. It has products, a cart, discount calculation, payment capture, and refund recording. No external services or real data are used.

Both design candidates must expose the same HTTP/API contract and pass the same current tests:

- Percentage coupon applies to eligible items.
- Discount cannot exceed subtotal.
- Checkout records subtotal, discount, total, and coupon ID.
- Full refund returns the captured total.
- Duplicate checkout requests are idempotent.

### Candidate A: coupled

Discount calculations and assumptions are duplicated or directly referenced in checkout, persistence, and refund flows. The implementation is clean enough to pass all current tests; it must not be made cartoonishly bad.

### Candidate B: modular

Discount behavior is represented through an explicit pricing/discount result and a stable policy interface. Checkout and refund depend on that result rather than reconstructing rules. It must not include code written specifically for the future scenarios.

Both candidates should have similar feature completeness and understandable code. The demo is invalid if one side contains deliberate bugs or advance knowledge of acceptance tests.

## The three futures

### F1 — Partial refund allocation

Requirement:

> Refund selected order items. The refunded discount must be allocated deterministically across items, and the sum of item refunds must equal the order refund without exceeding the captured amount.

Why it stresses the design: historical pricing decisions must remain available and consistent; recomputing a coupon from today's rules is unsafe.

Protected assertions include:

- Refund one discounted item.
- Refund items in two operations and preserve the total invariant.
- Handle rounding deterministically.
- Do not call the live discount policy during a refund.

### F2 — Organization-specific pricing policy

Requirement:

> A cart may belong to an organization with its own discount policy and maximum discount. Existing consumer checkout behavior must not change.

Why it stresses the design: policy selection should not spread conditional logic throughout the flow.

Protected assertions include:

- Consumer path remains identical.
- Two organizations can use different policies.
- Policy identity is recorded with the order.
- Unknown organization fails safely.

### F3 — Ordered discount composition

Requirement:

> Support an automatic organization discount and an optional coupon. The order of application is explicit, both components are recorded, and the combined discount never exceeds the subtotal.

Why it stresses the design: implicit scalar “discount amount” assumptions become visible.

Protected assertions include:

- The configured order changes the total predictably.
- Both component results are auditable.
- Caps apply to the combined result.
- Existing single-coupon behavior remains compatible.

## Present-day refactor loop

After the first matrix, Bob inspects only the evidence and proposes the smallest current change that could reduce repeated future friction. Expected direction, not a predetermined answer: persist an explicit pricing breakdown and route policy decisions through one interface.

The user reviews and approves the proposal. FutureFork applies it to Candidate A on a new candidate ref, reruns only F1, and displays before/after evidence. If the rerun does not improve, show that honestly.

## Three-minute video plan

**0:00–0:20 — Hook**

Show both candidates green today. Say: “Static review sees two correct implementations. But architecture is a bet on future change.”

**0:20–0:45 — Start rehearsal**

Select `coupled` and `modular`, show the three future cards, and start the run. Briefly show that IBM Bob receives identical task packets in isolated worktrees.

**0:45–1:35 — Reveal one future deeply**

Open partial refunds. Show the actual Bob-generated diffs and protected tests. Point to evidence, not adjectives: pass/fail, touched modules, reconstructed vs persisted pricing decisions, regressions, attempts.

**1:35–2:05 — Evidence matrix**

Show all three futures side by side. Clearly label observations and limitations. Avoid claiming the chosen architecture is universally better.

**2:05–2:35 — Close the loop**

Ask Bob for a minimal present-day refactor, show the patch, rerun F1, and compare the new evidence.

**2:35–2:55 — Why Bob matters**

Show Bob task history, Skill/MCP calls, and session evidence. Explain that Bob did the repo reasoning and future implementation; the deterministic runner judged outcomes.

**2:55–3:00 — Closing line**

> “FutureFork: let your code live through tomorrow before you merge it today.”

## Demo integrity rules

- Never fake a streaming run. If using prerecorded artifacts, label them “completed run.”
- Keep one small genuine live interaction available, such as opening an artifact or asking Bob to explain a linked diff.
- The displayed comparison must be generated from artifact files, not hardcoded UI data.
- Record failed attempts if they occurred; do not present manually curated success as autonomous output.

