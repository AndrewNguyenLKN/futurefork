---
name: future-fork
description: Rehearse the same hypothetical future change on isolated code candidates, preserve current behavior, and return evidence for an architecture decision.
---

# FutureFork workflow

Use this skill when the user asks to evaluate a design using FutureFork, run a future scenario, compare candidates, or test a present-day refactor against future-change evidence.

## Principles

- Treat every future requirement as a hypothesis, never a prediction.
- Keep candidate labels neutral.
- Never edit source candidate refs directly.
- Never read, edit, weaken, or delete evaluator-owned protected tests.
- Follow the same task template and limits for every candidate.
- Do not declare one architecture universally superior.
- Stop when limits are reached and preserve the failure honestly.

## Run one scenario

1. Read `CLAUDE.md`, the selected scenario, and the public task packet.
2. Call the FutureFork MCP preparation tool and confirm the returned worktree is isolated.
3. Inspect the candidate and state material assumptions in the run checkpoint.
4. Implement the smallest coherent solution inside allowed paths.
5. Preserve existing behavior and run the allowed development commands.
6. Do not search for hidden tests or modify FutureFork metadata.
7. Finalize editing through MCP.
8. Ask the evaluator to run protected tests.
9. Report the status and artifact links without rewriting the evaluator's result.

## Compare runs

Only compare runs with the same scenario hash, evaluator hash, limits, and compatible environment. Separate deterministic observations from interpretation. Cite artifact paths for every factual claim. Call out infrastructure failures and human interventions.

## Propose a present-day refactor

Use recurring evidence across multiple scenarios, not a single line-count difference. Propose the smallest change that preserves current behavior and plausibly addresses a repeated hotspot. Explain the hypothesis, request human approval, and evaluate it by rerunning the same frozen scenario. A failed improvement attempt is a valid result.

## Stop conditions

Stop and mark the run invalid if candidate refs are dirty, current-contract tests fail, protected assets change, required hashes differ, or the worktree is not isolated. Stop with `budget_exhausted` when the configured limit is reached; do not continue off-record.

