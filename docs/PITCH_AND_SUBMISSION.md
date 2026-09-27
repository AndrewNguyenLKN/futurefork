# Pitch and submission

## Working tagline

> FutureFork lets your code live through tomorrow before you merge it today.

## Honest current scope (read this before writing or recording anything)

The build is a working operator-driven pipeline (`futurefork prepare` / `futurefork finalize`)
with fail-closed protected-pack verification, and **one** frozen scenario (`partial-refund`) has
real, evaluated evidence on **both** candidates (`coupled`, `modular`). The other two frozen
scenarios (`organization-pricing`, `ordered-discounts`) have not been run on either candidate —
the 2×3 evidence matrix is not complete. There is no MCP server and no confirmed, instrumented
use of the `.bob/skills/future-fork/SKILL.md` file by Bob; both statements below describe only
what actually ran. The static evidence dashboard is at
[`docs/evidence-dashboard.html`](evidence-dashboard.html) — open it directly in a browser, no
server needed. Do not describe more than this in any submitted text, video, or slide.

## 30-second pitch

Two implementations can pass every test today and still respond very differently to the same
future change. FutureFork uses IBM Bob to implement one plausible future requirement on isolated
forks of both designs, runs a frozen, hidden acceptance test against each, and shows the real
diffs and results side by side — not an AI opinion about which design is "better," but a
reproducible record of what happened when each design was actually asked to change.

## Problem & Solution Statement (486 words)

Developers choose between competing designs using evidence that only covers the present: today's
tests pass, static review looks fine, and an experienced reviewer can *imagine* how the design
might hold up later. But imagining future maintenance is not the same as doing it, and doing it
by hand for every candidate design is too expensive to try before committing. The result is that
architectural bets are usually made on informed guesswork, and the actual cost of a design shows
up only after the team is already living with it.

FutureFork turns "how will this design respond to a future change?" into a bounded, reproducible
experiment instead of a guess. The developer supplies two Git refs that implement the same current
behavior and picks a frozen, plausible future requirement. FutureFork's CLI (`futurefork prepare`)
resolves the candidate to its exact commit, creates an isolated, detached Git worktree for it —
never touching the source ref — and writes a task packet containing the requirement, the public
acceptance criteria, and the exact public HTTP interface the change must expose. It deliberately
withholds the acceptance tests themselves. The developer opens that worktree in IBM Bob IDE and
runs the task packet; Bob does the actual implementation work.

Once Bob's task ends, `futurefork finalize` takes over deterministically: it freezes Bob's patch,
verifies the evaluator-owned protected test pack against a hash frozen before the run, mounts it
into the worktree only now, runs the project's existing regression suite and then the protected
acceptance tests, and re-verifies the protected pack's hash again afterward. Every result — the
patch, the test outcomes, the changed files, the timings, and the pack hashes before and after —
is written into one immutable, schema-validated run manifest. If the protected pack no longer
matches its frozen hash, the run is marked `oracle_tampered`, never a candidate result; if
FutureFork's own tooling fails, that is `runner_error`, never counted against the candidate. This
means the demo can show is not "an AI's opinion," but a real Git worktree, a real Bob task ID, a
real diff, and a real pass/fail result an engineer can open and re-check by hand.

The current build proves this end to end on one frozen scenario — partial refunds must allocate a
historical discount deterministically across items — run against two PocketCart candidates that
implement discounts differently (`coupled`: logic embedded across checkout/refund/persistence;
`modular`: a discount-policy interface). Both candidates pass the same 68–70 regression tests and
the same 34 hidden acceptance tests for that scenario, each with a distinct real Bob task and
Bobcoin spend, viewable in `docs/evidence-dashboard.html`. Two more frozen scenarios exist as
contracts, not yet run. FutureFork does not claim to predict which future will happen, does not
produce a maintainability score, and does not merge anything automatically — it gives developers
one thing they don't currently have: a real, inspectable rehearsal of the future change they were
only able to imagine before.

## Bob Usage Statement (190 words)

IBM Bob IDE is the implementer in FutureFork; nothing else writes the candidate code. FutureFork's
CLI (`futurefork prepare`) validates the candidate and scenario, then creates an isolated, retained
detached Git worktree for Bob to work in and writes a task packet with the requirement, acceptance
criteria, and public interface — never the acceptance tests. The developer opens that worktree in
Bob IDE and runs the task packet directly; there is no Bob API and no MCP server in this build, so
this handoff is manual and disclosed as such. Bob reads the code, plans, edits it, and (in one run)
also added its own development tests.

Two real Bob tasks exist. Task `d12b84c1a6a03a337b56b8594ebd6d2a` (5.40 Bobcoins) implemented
`partial-refund` on `modular`; its run had disclosed deviations (see
`artifacts/runs/p03-manual-modular-partial-refund/human-notes.md`), including oracle-informed
feedback given mid-run. Task `5c4c002baa472064dd11971c601c6436` (2.65 Bobcoins) implemented the
same frozen scenario on `coupled` through `futurefork finalize`, with zero disclosed interventions
and zero boundary violations. Both are indexed with real task-session screenshots in
`bob_sessions/INDEX.md`. `futurefork finalize` — not Bob, and not a human — independently ran the
tests, verified the protected pack's hash before and after, and wrote both results.

## 3-minute demo script (grounded in what actually exists)

**0:00–0:20 — The claim, stated narrowly.** "Two designs, same behavior today. I asked IBM Bob to
implement the same real future requirement on both, in isolated worktrees, and I have the real
results." Show `git branch -a` naming `coupled`/`modular`, or `docs/evidence-dashboard.html`'s
title banner, which states the scope (1 of 3 scenarios) up front.

**0:20–1:00 — One real task packet.** Open `artifacts/runs/20260927T123119Z-coupled-partial-refund/task-packet.md`
next to a Bob task-session screenshot from `bob_sessions/`. Point out the requirement, the public
interface, and that the acceptance tests are absent from it.

**1:00–2:10 — The dashboard.** Open `docs/evidence-dashboard.html` in a browser (double-click; no
server). Walk the scenario × candidate matrix (only `partial-refund` is filled in — say this out
loud). Walk the two cards: task ID, Bobcoins, regression and protected pass counts, changed files,
pack hash matching before/after, zero boundary violations for `coupled`, and the disclosed
deviations for `modular`. Click one artifact link (`patch.diff` or `manifest.json`) to prove it's
a real file, not a mockup.

**2:10–2:40 — What this is not.** Read the "does not support" list on the dashboard aloud: not a
maintainability score, not the full matrix, not a benchmark. This is the credibility moment — say
plainly that `organization-pricing` and `ordered-discounts` have not been run yet.

**2:40–3:00 — Close.** "FutureFork lets your code live through tomorrow before you merge it
today." Show the tagline on screen.

## Judging narrative

| Criterion | Real evidence to show |
|---|---|
| Application technology | `futurefork prepare`/`finalize` CLI, isolated `WorktreeManager` worktrees, fail-closed protected-pack verification, a strict Pydantic run-manifest schema, a static offline evidence dashboard |
| Presentation | One real frozen scenario run cleanly on both candidates, with real Bob task IDs and screenshots |
| Business value | Concrete, inspectable evidence for one architectural decision point, instead of static review alone |
| Originality | Using an AI coding agent's actual future-maintenance work, under a protected hidden oracle, as the evaluation instrument — not an AI judgment call |

The event page lists these categories but does not publish weights; do not invent weights.

## Required submission assets

See [`SUBMISSION_READY.md`](../SUBMISSION_READY.md) for the exact present/missing status of every
item below.

- Public code repository.
- Demo URL if available (this build has none; the dashboard is a local static file).
- Cover image.
- Slide deck.
- MP4 working demo, minimum 90 seconds and maximum 3 minutes.
- Problem & Solution Statement, maximum 500 words (above: 486).
- Bob Usage Statement, maximum 500 words (above: 190).
- Bob task-session summary screenshots for every material task in `bob_sessions/`.

## Final repository checklist

- [ ] Fresh clone setup succeeds from README instructions.
- [x] Both demo candidates and the one shown run (`partial-refund` × `coupled`/`modular`) are reproducible from artifacts on disk.
- [x] Secret-pattern scan was clean immediately before the submission commit; the commit uses a GitHub noreply author email.
- [x] No public-data sources to list: PocketCart is 100% synthetic/fictional data, and the runtime uses no external services or third-party datasets.
- [x] All metrics shown in the dashboard/video exist in artifact files (`docs/evidence-dashboard.html` is generated from `artifacts/runs/` and `bob_sessions/`, nothing hand-typed).
- [x] Failed and human-assisted runs are labeled honestly (the `modular` run's deviations are shown on the dashboard, not hidden).
- [x] Bob session PNGs are present and indexed for both material tasks.
- [x] The Bob Usage Statement above matches what actually happened (two manual Bob IDE tasks; no MCP server; no confirmed Skill usage).
- [x] License is included (`LICENSE`, MIT).
- [x] Cover image and six-slide deck are finished and reviewed; deck package/layout validation reports zero findings and zero warnings.
- [x] Local video is verified as 1920×1080 H.264 + AAC and 175.37 seconds; verify playback once more after the form upload.
- [x] lablab.ai one-person team **Single Thread** exists with one member.
- [ ] Submission is completed before **27 September 2026, 22:00 Vietnam / 23:00 Singapore**.
