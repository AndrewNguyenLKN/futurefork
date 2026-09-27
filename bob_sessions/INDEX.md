# Bob session evidence index

Add one row immediately after capturing each task-session consumption summary. Store screenshots as PNG files in this directory.

| Task | Purpose | Scenario/candidate | Related commit | Screenshot |
|---|---|---|---|---|
| 01 | Read-only onboarding: verify Bob understands the product contract, rules, repository state, P0 tasks, and winning risks | Project-wide / no code candidate | N/A — read-only task | `futurefork_task01_onboarding_summary.png` |
| 02 | Manual P0.3 proof: implement and correct deterministic item-level partial refunds | `partial-refund` / candidate A (`modular`) | Starting ref `f9e3ecda1e4a8452678578226b2553a6ebddf536`; final patch preserved in `artifacts/runs/p03-manual-modular-partial-refund/patch.diff` | `futurefork_task02_p03_modular_partial_refund_summary.png` |
| 03 | P0.8 evidence run: implement deterministic item-level partial refunds under the frozen task packet | `partial-refund` / candidate B (`coupled`) | Starting ref `11f9d4e8559ec56fc818b9b9e72c2150e9560931`; clean final bundle in `artifacts/runs/20260927T123119Z-coupled-partial-refund/` | `futurefork_task03_p08_coupled_partial_refund_summary.png` |

Task 01 metadata:

- Task ID: `5db93be60bab1c835d6a584a8e2f29c8`
- Workspace: `IBM`
- Bobcoins: `0.384`
- Context: `38.2k / 270.0k (14%)`
- Result: Bob identified **P0.1 — Freeze the demo contract** as the single best first implementation task.

Task 02 metadata:

- Task ID: `d12b84c1a6a03a337b56b8594ebd6d2a`
- Workspace: `futurefork-p03-modular`
- Bobcoins: `5.40`
- Context: `104.2k / 270.0k (39%)`
- Result: Bob implemented the `partial-refund` scenario on candidate A. Independent evaluation passed the public regression suite **68/68** and the frozen protected pack **34/34**. The run includes disclosed human intervention, oracle-informed feedback, and recovery from an operator cleanup error; see `artifacts/runs/p03-manual-modular-partial-refund/human-notes.md`.

Task 03 metadata:

- Task ID: `5c4c002baa472064dd11971c601c6436`
- Workspace: `20260927T121718Z-coupled-partial-refund`
- Bobcoins: `2.65`
- Context: `59.6k / 270.0k (22%)`
- Result: Bob implemented the same frozen `partial-refund` scenario on candidate B and added 23 focused tests. Independent evaluation passed the public regression suite **70/70** and the frozen protected pack **34/34**, with **7 changed files**, **558 lines added**, **23 lines deleted**, and **no boundary violations**. The authoritative clean bundle is `artifacts/runs/20260927T123119Z-coupled-partial-refund/`.

Do not add placeholder images or fabricate task records. Delete the pending row once real evidence exists.
