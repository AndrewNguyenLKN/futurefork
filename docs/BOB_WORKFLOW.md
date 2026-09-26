# IBM Bob workflow and evidence plan

## Why Bob is core

Bob performs the work FutureFork is designed to observe:

- Understands each candidate repository.
- Interprets the future requirement.
- Plans and implements the change in an isolated worktree.
- Uses project documentation and tests while iterating.
- Reads the resulting evidence and proposes a minimal present-day refactor.

FutureFork's deterministic runner creates isolation, executes protected tests, and records evidence. Without Bob, there is no architecture rehearsal; without the runner, Bob would be grading its own work.

## Planned Bob integration

### Project Skill

`.bob/skills/future-fork/SKILL.md` defines the repeatable workflow, constraints, stop conditions, and evidence expectations. It prevents each experiment from depending on a hand-crafted prompt.

### Local MCP server

Bob calls the FutureFork MCP server to prepare worktrees, finalize editing, execute protected evaluation, and retrieve artifacts. Project MCP configuration should live in `.bob/mcp.json` when implemented.

### Agent mode and parallel tasks

Each candidate × scenario experiment is independent after inputs are frozen. Use separate Bob tasks, and parallelize only after the single-run path is trustworthy. The comparison and refactor recommendation happen after all required run artifacts exist.

## Standard task packet

Every run should give Bob the same template:

```text
You are implementing one hypothetical future requirement in an isolated
FutureFork experiment.

Candidate: {{candidate_label}}
Scenario: {{scenario_id}}
Requirement: {{requirement}}
Public acceptance criteria: {{criteria}}
Editable paths: {{editable_paths}}
Commands allowed: {{commands}}
Limits: {{limits}}

Implement the smallest coherent solution. Preserve current behavior. You may
add development tests, but evaluator-owned tests are hidden and immutable.
Do not change FutureFork metadata, limits, or protected paths. Record material
assumptions. Stop when tests pass or the experiment limit is reached.
```

Candidate labels should be neutral (`A`, `B`) when possible.

## Bobcoin budget

The hackathon account provides 40 Bobcoins per participant. For a solo participant, treat that as a hard budget with no top-up.

Suggested allocation:

| Work | Target Bobcoins |
|---|---:|
| Repository and seed-app planning | 4 |
| Runner/MCP implementation | 8 |
| Six required future runs | 18 |
| Refactor proposal and rerun | 5 |
| Debugging reserve | 3 |
| Final explanation/submission polish | 2 |

This is a planning allocation, not a guaranteed consumption schedule. Check actual usage in Bob IDE under Settings → General or the admin dashboard.

Conserve coins by keeping deterministic replay, report rendering, hashing, and test execution outside AI calls. Do not repeatedly ask Bob to restate information already saved in artifacts.

## Required session evidence

For every material task:

1. In Bob IDE chat, open **Tasks**.
2. Select the task.
3. Click the task header to open the session consumption summary.
4. Save a PNG in `bob_sessions/`.

Naming convention:

```text
futurefork_task01_seed_app_summary.png
futurefork_task02_runner_mcp_summary.png
futurefork_task03_candidate_a_partial_refund_summary.png
futurefork_task04_candidate_b_partial_refund_summary.png
...
```

Also keep `bob_sessions/INDEX.md` updated with task purpose, related commit, scenario, and filename.

## Evidence integrity

- Screenshots must come from actual Bob tasks.
- Do not crop away task identity or consumption summary needed to establish provenance.
- Do not claim code was produced by Bob if it was produced elsewhere.
- If another tool assists, disclose its role and keep Bob responsible for a material core workflow.
- The final Bob Usage Statement must match the repository evidence.

## Account checks

- Use the hackathon-provisioned Bob account, not a personal allocation.
- Confirm the selected account/region matches the organizer invitation.
- Use Bob IDE v2.0.2 or later; v1.0.3 and v2.0.0 were announced to stop working on 30 September.

