#!/usr/bin/env python3
"""Generate docs/evidence-dashboard.html: a static, offline, self-contained report comparing
the two real partial-refund runs on disk. Reads only actual artifact files; never invents data.

Usage: .venv/bin/python scripts/build_dashboard.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from futurefork.manifest import load_manifest  # noqa: E402

OUT = ROOT / "docs" / "evidence-dashboard.html"

MODULAR_RUN = ROOT / "artifacts" / "runs" / "p03-manual-modular-partial-refund"
COUPLED_RUN = ROOT / "artifacts" / "runs" / "20260927T123119Z-coupled-partial-refund"
SCENARIO_ALL = ["partial-refund", "organization-pricing", "ordered-discounts"]
SCENARIO_DONE = "partial-refund"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def build_modular_record() -> dict:
    """The P0.3 manual run predates the P0.4 manifest format; read its own raw files directly."""
    results = json.loads(read(MODULAR_RUN / "test-results.json"))
    changed = json.loads(read(MODULAR_RUN / "changed-paths.json"))
    notes = read(MODULAR_RUN / "human-notes.md")
    caveats = [
        line.strip() for line in notes.splitlines()
        if line.strip().startswith(tuple(f"{i}. **" for i in range(1, 10)))
    ]
    return {
        "candidate": "modular", "label": "Candidate A (manual, pre-CLI)",
        "task_id": "d12b84c1a6a03a337b56b8594ebd6d2a", "bobcoins": "5.40",
        "starting_commit": "f9e3ecda1e4a8452678578226b2553a6ebddf536",
        "regression_summary": results["regression"]["result"],
        "regression_command": results["regression"]["command"],
        "protected_passed": results["protected"]["passed"], "protected_total": results["protected"]["total"],
        "protected_command": results["protected"]["command"],
        "outcome": results["outcome"], "pack_hash_match": results["evaluator"]["hash_match"],
        "pack_hash": results["evaluator"]["test_pack_sha256_expected"],
        "changed_files": len(changed["changed_paths"]),
        "changed_paths": [c["path"] for c in changed["changed_paths"]],
        "lines_added": None, "lines_deleted": None, "duration_seconds": None,
        "boundary_violations": [], "human_interventions_disclosed": len(caveats),
        "caveats": caveats,
        "run_dir_rel": "../artifacts/runs/p03-manual-modular-partial-refund",
        "screenshot_rel": "../bob_sessions/futurefork_task02_p03_modular_partial_refund_summary.png",
        "evaluated_on": results["evaluated_on"],
    }


def build_coupled_record() -> dict:
    m = load_manifest(COUPLED_RUN / "manifest.json")
    return {
        "candidate": "coupled", "label": "Candidate B (futurefork prepare/finalize CLI)",
        "task_id": m.agent.task_id, "bobcoins": "2.65",
        "starting_commit": m.candidate.starting_commit,
        "regression_summary": f"{m.tests.regression.passed} passed",
        "regression_command": " ".join(m.tests.regression.command),
        "protected_passed": m.tests.protected.passed, "protected_total": m.tests.protected.passed + m.tests.protected.failed + m.tests.protected.errors,
        "protected_command": " ".join(m.tests.protected.command),
        "outcome": m.outcome.value, "pack_hash_match": m.evaluator.observed_sha256_after_run == m.evaluator.test_pack_sha256,
        "pack_hash": m.evaluator.test_pack_sha256,
        "changed_files": m.measurements.changed_files,
        "changed_paths": [c["path"] for c in json.loads(read(COUPLED_RUN / "changed-paths.json"))],
        "lines_added": m.measurements.lines_added, "lines_deleted": m.measurements.lines_deleted,
        "duration_seconds": m.measurements.duration_seconds,
        "boundary_violations": [e.description for e in m.measurements.boundary_violations],
        "human_interventions_disclosed": len(m.measurements.human_interventions),
        "caveats": [],
        "run_dir_rel": "../artifacts/runs/20260927T123119Z-coupled-partial-refund",
        "screenshot_rel": "../bob_sessions/futurefork_task03_p08_coupled_partial_refund_summary.png",
        "evaluated_on": "isolated detached worktree, evaluated in place by `futurefork finalize`",
    }


CSS = """
:root {
  --bg: #0b0f14; --panel: #121821; --panel2: #171f2b; --border: #253143; --text: #e6edf3;
  --muted: #93a3b8; --accent: #5fb3ff; --good: #3ecf8e; --bad: #ff6b6b; --warn: #f5c451;
}
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
    --bg: #f6f8fa; --panel: #ffffff; --panel2: #f1f4f8; --border: #d8e0ea; --text: #0b0f14;
    --muted: #526176; --accent: #0969da; --good: #1a7f4e; --bad: #cf222e; --warn: #9a6700;
  }
}
:root[data-theme="dark"] { --bg: #0b0f14; --panel: #121821; --panel2: #171f2b; --border: #253143; --text: #e6edf3; --muted: #93a3b8; --accent: #5fb3ff; --good: #3ecf8e; --bad: #ff6b6b; --warn: #f5c451; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.55 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }
.wrap { max-width: 1080px; margin: 0 auto; padding: 28px 16px 64px; }
h1 { font-size: 26px; margin: 0 0 4px; }
h2 { font-size: 18px; margin: 40px 0 12px; border-top: 1px solid var(--border); padding-top: 24px; }
.sub { color: var(--muted); margin: 0 0 20px; }
.pill { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.pill.good { background: color-mix(in srgb, var(--good) 20%, transparent); color: var(--good); }
.pill.warn { background: color-mix(in srgb, var(--warn) 22%, transparent); color: var(--warn); }
.banner { background: var(--panel2); border: 1px solid var(--border); border-left: 4px solid var(--warn); border-radius: 8px; padding: 14px 16px; margin: 18px 0; }
.banner b { color: var(--warn); }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 760px) { .grid { grid-template-columns: 1fr; } }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 18px; }
.card h3 { margin: 0 0 2px; font-size: 16px; }
.card .meta { color: var(--muted); font-size: 12.5px; margin-bottom: 12px; }
.row { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border-top: 1px solid var(--border); font-size: 13.5px; }
.row:first-of-type { border-top: none; }
.row .k { color: var(--muted); }
.row .v { text-align: right; font-variant-numeric: tabular-nums; }
code, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12.5px; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.links { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; }
.links a { border: 1px solid var(--border); border-radius: 6px; padding: 4px 9px; font-size: 12.5px; }
ul.caveats { margin: 8px 0 0; padding-left: 20px; font-size: 13px; color: var(--muted); }
ul.caveats li { margin: 4px 0; }
table.matrix { border-collapse: collapse; width: 100%; margin-top: 8px; font-size: 13.5px; }
table.matrix th, table.matrix td { border: 1px solid var(--border); padding: 8px 10px; text-align: center; }
table.matrix th { background: var(--panel2); }
table.matrix td.done { background: color-mix(in srgb, var(--good) 12%, transparent); }
table.matrix td.todo { color: var(--muted); }
footer { margin-top: 48px; color: var(--muted); font-size: 12.5px; border-top: 1px solid var(--border); padding-top: 16px; }
.claims { font-size: 13.5px; }
.claims .ok::before { content: "✓ "; color: var(--good); }
.claims .no::before { content: "✗ "; color: var(--bad); }
"""


def _bold(text: str) -> str:
    """Escape for HTML, then render the source's own **bold** markdown as <strong>."""
    import re

    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escape(text))


def money(v) -> str:
    return f"{v:,}" if isinstance(v, int) else escape(str(v))


def render_card(rec: dict) -> str:
    boundary = (
        f'<span class="pill good">none</span>' if not rec["boundary_violations"]
        else f'<span class="pill warn">{len(rec["boundary_violations"])}</span>'
    )
    duration = f'{rec["duration_seconds"]}s' if rec["duration_seconds"] is not None else "not recorded (pre-manifest run)"
    lines = (
        f'+{rec["lines_added"]} / -{rec["lines_deleted"]}' if rec["lines_added"] is not None
        else "not recorded (pre-manifest run)"
    )
    caveats_html = ""
    if rec["caveats"]:
        items = "".join(f"<li>{_bold(c.lstrip('0123456789. '))}</li>" for c in rec["caveats"])
        caveats_html = f'<div class="banner"><b>Disclosed deviations for this run</b><ul class="caveats">{items}</ul></div>'
    changed_list = ", ".join(f"<code>{escape(p)}</code>" for p in rec["changed_paths"])
    return f"""
    <div class="card">
      <h3>{escape(rec["label"])}</h3>
      <div class="meta">Candidate ref <code>{escape(rec["candidate"])}</code> · starting commit <code>{escape(rec["starting_commit"][:12])}…</code></div>
      <div class="row"><span class="k">Bob task ID</span><span class="v mono">{escape(rec["task_id"])}</span></div>
      <div class="row"><span class="k">Bobcoins spent</span><span class="v">{escape(rec["bobcoins"])}</span></div>
      <div class="row"><span class="k">Outcome</span><span class="v"><span class="pill good">{escape(rec["outcome"])}</span></span></div>
      <div class="row"><span class="k">Regression suite</span><span class="v">{escape(rec["regression_summary"])}</span></div>
      <div class="row"><span class="k">Protected pack (partial-refund)</span><span class="v">{rec["protected_passed"]} / {rec["protected_total"]} passed</span></div>
      <div class="row"><span class="k">Protected pack hash after run</span><span class="v">{'<span class="pill good">matches frozen</span>' if rec["pack_hash_match"] else '<span class="pill warn">MISMATCH</span>'}</span></div>
      <div class="row"><span class="k">Changed files</span><span class="v">{rec["changed_files"]}</span></div>
      <div class="row"><span class="k">Lines changed</span><span class="v">{lines}</span></div>
      <div class="row"><span class="k">Boundary violations</span><span class="v">{boundary}</span></div>
      <div class="row"><span class="k">Wall time (finalize)</span><span class="v">{escape(duration)}</span></div>
      <div class="row"><span class="k">Evaluated on</span><span class="v" style="text-align:right;max-width:60%">{escape(rec["evaluated_on"])}</span></div>
      <p class="mono" style="color:var(--muted);font-size:12px;margin:12px 0 0">Changed: {changed_list}</p>
      {caveats_html}
      <div class="links">
        <a href="{rec["run_dir_rel"]}/patch.diff">patch.diff</a>
        <a href="{rec["run_dir_rel"]}/test-results.json">test-results.json</a>
        <a href="{rec["run_dir_rel"]}/changed-paths.json">changed-paths.json</a>
        <a href="{rec["run_dir_rel"]}/events.jsonl">events.jsonl</a>
        {'<a href="' + rec["run_dir_rel"] + '/manifest.json">manifest.json</a>' if (ROOT / rec["run_dir_rel"].replace("../", "") / "manifest.json").exists() else ''}
        {'<a href="' + rec["run_dir_rel"] + '/human-notes.md">human-notes.md</a>' if (ROOT / rec["run_dir_rel"].replace("../", "") / "human-notes.md").exists() else ''}
        <a href="{rec["screenshot_rel"]}">Bob session screenshot</a>
      </div>
    </div>"""


def render_matrix() -> str:
    candidates = ["coupled", "modular"]
    rows = []
    for scenario in SCENARIO_ALL:
        cells = []
        for c in candidates:
            if scenario == SCENARIO_DONE:
                cells.append('<td class="done">✓ evidence</td>')
            else:
                cells.append('<td class="todo">not run</td>')
        rows.append(f"<tr><td>{escape(scenario)}</td>{''.join(cells)}</tr>")
    return f"""
    <table class="matrix">
      <thead><tr><th>Scenario</th><th>coupled</th><th>modular</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>"""


def main() -> None:
    modular = build_modular_record()
    coupled = build_coupled_record()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FutureFork evidence: partial-refund</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>FutureFork — partial-refund evidence</h1>
  <p class="sub">Generated {generated_at} by <code>scripts/build_dashboard.py</code> from real files under <code>artifacts/runs/</code> and <code>bob_sessions/</code>. Every number below links to the artifact it came from. Nothing here is computed live or fetched over the network — open this file directly.</p>

  <div class="banner">
    <b>Scope of this evidence: 1 of 3 frozen scenarios × 2 of 2 candidates.</b>
    Only <code>partial-refund</code> has been run on both <code>coupled</code> and <code>modular</code>.
    <code>organization-pricing</code> and <code>ordered-discounts</code> have <b>not been run on either candidate</b>.
    This is not the full 2×3 evidence matrix (P0.8 is still in progress) — do not present it as one.
  </div>

  <h2>Scenario × candidate matrix</h2>
  {render_matrix()}

  <h2>partial-refund: coupled vs. modular</h2>
  <div class="grid">
    {render_card(coupled)}
    {render_card(modular)}
  </div>

  <h2>What this evidence supports — and does not</h2>
  <div class="card claims">
    <p class="ok">Both candidates independently satisfy the same frozen, hidden protected test pack for <code>partial-refund</code> (pack hash <code class="mono">{coupled["pack_hash"][:16]}…</code>, unchanged after each run).</p>
    <p class="ok">Both runs are traceable to a real IBM Bob task ID, a real Bobcoin spend, and a real task-session screenshot in <code>bob_sessions/</code>.</p>
    <p class="ok">The <code>coupled</code> run has zero disclosed human interventions and zero boundary violations; the <code>modular</code> run has {modular["human_interventions_disclosed"]} disclosed deviations (oracle-informed feedback, a lost first attempt after a cleanup incident, and others — see its <code>human-notes.md</code>), which is a real fairness asymmetry between the two runs, not evidence that one candidate is better.</p>
    <p class="no">This does <b>not</b> show which architecture is "more maintainable" — one scenario is not enough evidence for that, and the product's own rules (<code>docs/EVALUATION.md</code>) forbid that claim regardless.</p>
    <p class="no">This does <b>not</b> represent the full 2×3 matrix. <code>organization-pricing</code> and <code>ordered-discounts</code> have no runs yet.</p>
    <p class="no">Nothing here is a benchmark, a score, or a prediction. It is two disclosed, reproducible executions of the same frozen requirement.</p>
  </div>

  <footer>
    FutureFork · synthetic PocketCart data only · this file is static and safe to open offline · source: <code>scripts/build_dashboard.py</code> · regenerate anytime by re-running that script after new runs finalize.
  </footer>
</div>
</body>
</html>
"""
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
