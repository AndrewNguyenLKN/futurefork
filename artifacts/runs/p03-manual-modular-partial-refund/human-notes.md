# P0.3 manual run — notes (human/operator annotations; original artifacts are not edited)

Run: candidate `modular` (label A) × `partial-refund`, manual, human-triggered Bob task in Bob IDE.

## Outcome (evaluator-observed)

- Public regression suite: 68 passed. Protected `partial-refund` pack: **34 / 34 passed**, pack hash unchanged after the run.
- Outcome class: `completed`, with the caveats below. This is one bounded, manual experiment on one candidate; it says nothing about `coupled` and is not evidence about architecture quality.
- First real evidence that the protected pack is satisfiable.

## Provenance of each fact

`events.jsonl` tags every event `verified` (observed on disk by the evaluator in this session), `reported` (taken from the previous operator's transcript, not independently verifiable, and its raw output was not preserved) or `incident`. Do not upgrade `reported` events to facts in the Bob Usage Statement without confirming them in Bob IDE.

## Deviations from the fair-comparison protocol (must be disclosed)

1. **Oracle-informed feedback.** After the first oracle run, Bob was told the response status must be `refunded`. The value is in the frozen public interface, but the trigger was a protected-test failure. If the same treatment is not given to every candidate × scenario run, the comparison is unequal. Decide one policy (feedback allowed, counted as an attempt, for all runs; or no feedback) before running `coupled`.
2. **Lost attempt-1 patch.** A cleanup bug deleted the worktree (see incident). The final implementation is Bob's re-application from its own task history, not the original attempt-1 output, so attempt 1 cannot be inspected. The 33/34 first result is reported only.
3. **Bob could not run tests.** Bob's Python has no pytest, so its development tests were run by the operator from outside the worktree. Bob still wrote them. Give the next run the same arrangement or fix the environment for both.
4. **Boundary probing.** Bob reportedly inspected system Python paths (outside the workspace). Reportedly no FutureFork repo or pack access; not verifiable from artifacts.
5. **Packet fidelity.** The task packet's illustrative response used `"order_id": "ord_0001"`, but real ids are `order_0001`. It did not affect the result but the packet was not generated from the frozen YAML byte for byte.
6. **Unmount bug.** Do not reuse the earlier unmount snippet. Evaluation now happens on a snapshot copy; the oracle is never mounted in Bob's worktree.

## Still needed from the user

- Save the **task-session summary screenshot** of Bob task `d12b84c1a6a0…` (Bobcoins 5.40, workspace `futurefork-p03-modular`) as `bob_sessions/futurefork_task02_p03_modular_partial_refund_summary.png`, then add its row to `bob_sessions/INDEX.md`. (The Task panel is currently open in Bob.) No placeholder has been created.
- Remaining budget if only the onboarding (0.384) and this task (5.40) have been spent: 40 − 5.784 = 34.216 Bobcoins. Confirm in the Bob dashboard.
