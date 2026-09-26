# Evaluation protocol

## The question being evaluated

FutureFork does not evaluate “which architecture is best?” It evaluates:

> Under a frozen set of future scenarios and equal execution conditions, what observable work and outcomes occurred when IBM Bob attempted to evolve Candidate A and Candidate B?

## Fair-comparison protocol

Before execution:

1. Confirm both candidates implement the same current behavior.
2. Run the same current test suite on both.
3. Freeze scenario text, protected tests, toolchain, limits, and Bob instruction template.
4. Hash all frozen inputs.
5. Ensure neither candidate contains scenario-specific code or acceptance-test knowledge.

During execution:

1. Use clean, isolated worktrees.
2. Give Bob the same information and limits.
3. Do not offer hints to only one candidate.
4. Record human intervention as an event.
5. Stop at the same time/attempt limit.

After execution:

1. Run evaluator-owned tests without permitting edits.
2. Verify their hashes.
3. Preserve unsuccessful patches and logs.
4. Compute measurements mechanically from artifacts.
5. Let Bob explain only after raw results exist.

## Primary evidence

These decide whether a scenario was implemented:

- Protected acceptance tests.
- Existing regression tests.
- Build/typecheck/lint only where they are part of the frozen contract.
- Tamper and scope checks.

## Secondary evidence

These help interpret change friction but do not independently decide quality:

- Files and logical modules changed.
- Public interface churn.
- Cross-scenario hotspot overlap.
- Added/deleted lines.
- Attempts, elapsed time, and tool calls.
- Bob's explanation of obstacles.

Do not imply that fewer lines always means better design, or that longer time always means worse architecture.

## MVP experiment matrix

| Scenario | Coupled candidate | Modular candidate |
|---|---:|---:|
| Partial refund | Required | Required |
| Organization pricing | Required | Required |
| Ordered discounts | Required | Required |

After the matrix, rerun partial refund on the human-approved refactored candidate.

## Baselines

The minimal baseline is ordinary present-day evidence:

- Both candidates pass the same current tests.
- A static diff/review does not execute future requirements.

FutureFork adds future-change execution. Do not claim that static review is incapable of anticipating the issues; compare what each process actually surfaces in this demo.

## Stronger optional tests

- **Held-out future:** freeze both designs before revealing a fourth scenario.
- **Neutral future:** a change expected to affect both designs similarly.
- **Repeated run:** run one candidate/scenario at least three times to show agent variance.
- **Swap order:** alternate which candidate Bob handles first.
- **Blind labels:** present candidates as A/B during Bob interpretation to reduce narrative bias.

## What may be claimed

Acceptable:

- “In our three frozen PocketCart scenarios, Candidate B passed all protected tests while touching fewer pricing modules.”
- “Candidate A required changes in checkout, refund, and persistence in two of three runs.”
- “After the approved refactor, the partial-refund run passed within the same limits.”

Not acceptable:

- “Candidate B is 73% more maintainable.”
- “FutureFork predicts future technical debt.”
- “This design will save six months of work.”
- “The system proves the architecture is safe.”

## Reporting failures

Infrastructure failure must be labeled separately and must not make a candidate look worse. Budget exhaustion is an experimental outcome, not proof the change is impossible. If Bob produces different outcomes across repeats, show the distribution and reduce the strength of the conclusion.

