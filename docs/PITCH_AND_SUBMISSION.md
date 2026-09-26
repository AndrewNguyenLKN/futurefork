# Pitch and submission plan

## Working tagline

> FutureFork lets your code live through tomorrow before you merge it today.

## 30-second pitch

Two implementations can pass every test today and still create very different futures. FutureFork uses IBM Bob to implement the same plausible roadmap changes on isolated forks of both designs. It runs protected acceptance tests and shows the real diffs, regressions, hotspots, and attempts side by side. Instead of asking AI whether an architecture looks maintainable, FutureFork asks AI to maintain it—then lets independent evidence inform the developer's decision.

## Problem & Solution Statement draft

Developers make architectural decisions with incomplete evidence. Unit tests tell us whether code works today; static review can identify risks; experienced engineers can imagine future changes. But the cost of actually prototyping several futures usually makes those consequences invisible until the system must evolve.

FutureFork turns future change into a bounded experiment. A developer provides two code candidates that implement the same current behavior and selects plausible future requirements from the roadmap. In isolated Git worktrees, IBM Bob receives the same scenario, constraints, and time budget for each candidate and implements the change. FutureFork then applies evaluator-owned acceptance tests, preserves the generated patches and logs, and displays a side-by-side evidence matrix: which scenarios passed, which modules changed, where public interfaces moved, what regressions occurred, how many attempts were needed, and where multiple futures repeatedly touched the same hotspots.

The user—not the model—makes the design decision. FutureFork does not predict which requirements will occur or claim a universal maintainability score. Its conclusions are explicitly scoped to the selected scenarios, agent, and limits. Bob can then propose one small present-day refactor, which the developer approves and FutureFork reruns to see whether the evidence actually improves.

Our PocketCart demo compares two equally correct discount implementations across partial refunds, organization pricing, and discount composition. The result is not another AI opinion about code quality; it is a reproducible rehearsal of maintaining both designs.

## Bob Usage Statement draft

IBM Bob IDE is the core implementation agent in FutureFork. A project Skill gives Bob a repeatable architecture-rehearsal workflow, while a local MCP server prepares isolated Git worktrees, freezes scenario inputs, records checkpoints, executes evaluator-owned tests, and returns artifacts.

For each candidate and future scenario, Bob reads the repository, interprets the requirement, plans the change, edits code, adds development tests where useful, and iterates within the same limits. FutureFork's deterministic runner then prevents Bob from editing the protected acceptance tests and independently records the final diff, regression results, scenario results, attempts, timing, and provenance. After the comparison exists, Bob reads those artifacts and proposes a minimal present-day refactor. A human explicitly approves the refactor, and the same scenario is rerun to test whether the evidence changes.

We use Bob Skills to keep instructions consistent, MCP tools to connect Bob to the experiment runner, and separate tasks for independent candidate/scenario runs. Deterministic replay, hashing, test execution, and report rendering do not consume Bob reasoning calls. This makes Bob responsible for the work being evaluated while preventing it from grading its own implementation.

Every material Bob task has a task-session consumption summary screenshot under `bob_sessions/`, with an index linking the task to its scenario and repository commit.

Revise this statement to match the final implementation exactly; remove any feature that was not actually used.

## Judging narrative

| Criterion | Evidence to show |
|---|---|
| Application technology | Bob Skill + MCP, isolated worktrees, protected oracle, immutable artifact trail |
| Presentation | Two green candidates today → divergent future evidence → tested refactor loop |
| Business value | Earlier evidence for costly design decisions; clearer review and roadmap planning |
| Originality | Use AI-generated future maintenance work as an architecture evaluation instrument |

The event page lists these categories but does not publish weights; do not invent weights.

## Required submission assets

- Public code repository.
- Demo URL if available.
- Cover image.
- Slide deck.
- MP4 working demo, minimum 90 seconds and maximum 3 minutes.
- Problem & Solution Statement, maximum 500 words.
- Bob Usage Statement, maximum 500 words.
- Bob task-session summary screenshots for every participant/material task in `bob_sessions/`.

## Final repository checklist

- [ ] Fresh clone setup succeeds from README instructions.
- [ ] Both demo candidates and every shown run are reproducible.
- [ ] No secret, token, private URL, personal data, or client data exists in Git history.
- [ ] Public-data sources and licenses are listed; preferably use only synthetic demo data.
- [ ] All metrics shown in video exist in artifact files.
- [ ] Failed and human-assisted runs are labeled honestly.
- [ ] Bob session PNGs are present and indexed.
- [ ] The Bob Usage Statement matches what actually happened.
- [ ] License is included.
- [ ] Video length and playback are verified after upload.
- [ ] Submission is completed before **27 September 2026, 22:00 Vietnam / 23:00 Singapore**.

