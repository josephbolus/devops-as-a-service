# Demo run-of-show — DevOps as a Service

Timed rehearsal sheet for the Nov 2 recording (sprint Day 7). This is
the operator's sheet, not the script: the words live in the demo
script; this sheet pins **where to click, what stage must be on
screen, how long each beat may take, and which fallback artifact to
cut to** if a beat fails. Pinned by
`hackathon-agent-scaffold/tests/test_demo_run_of_show.py`.

Honest status: **Not yet recorded.** No video exists yet. This sheet
exists so the two required Nov 2 takes (primary + backup, same day)
run identically and every fallback is a walkable artifact, not a
memory.

## Surface: the demo console

Run the demo from the demo console, not a bare terminal:

```bash
cd hackathon-agent-scaffold && python3 demo_ui.py --port 8765
# then open http://127.0.0.1:8765/ at 1080p, browser zoom 125%
```

`demo_ui.py` shows an issue picker (Tier 1/2/3 + guardrail), a
Mock/Live toggle, and a stage timeline that fills in live via
`pipeline.run`'s `on_event` hook, in this exact order:

guardrail → triage → plan → code → tests → review → done

The "Try to break it" panel posts arbitrary text to the
deterministic guardrail; an escalation renders the human-approval
handoff (0 model calls, no files changed, no PR — plus the human's
three options) from `daas/approval.py`.

Safety on recording day: Mock runs and Live-without-PR runs execute
against a throwaway copy of the demo repo — the pristine repo is
never mutated. Only Live + "Open real PR" touches the real repo.

## Pre-flight (complete before pressing record)

- [ ] Rehearse once end-to-end in Mock mode (Tier 1): all seven
      stages fill in order, tests show 6 → 7, reviewer approves.
- [ ] Rehearse the trust beat once: "Try to break it" with
      "Delete the legacy database and drop old tables." — the
      guardrail stage blocks, the approval handoff renders, and the
      status line reads escalated with no agent run.
- [ ] Open every fallback artifact once at 125% zoom (see table
      below) — diff text must be readable at 1080p.
- [ ] Confirm `demo-fallbacks/live/tier1-pr16/PROVENANCE.md` still
      matches GitHub for PR #16; update the capture if it moved.
- [ ] Tier-1 issue text ready to paste, not typed live. No real
      client names, repos, or data anywhere on screen.
- [ ] Eval scorecard open in a tab: `eval-scorecard/SCORECARD.md`.
- [ ] For Live runs, the split configuration is set in the console's
      environment (the Oct 25 measured decision, `split-runs.json`):
      `DAAS_MODEL_CODER=muse-wonder-1.0` and
      `DAAS_MODEL_REVIEWER=muse-wonder-1.0`; TRIAGE/PLANNER stay on
      the `muse-spark-1.3` default.

## Timed beats (2:30–3:00 total)

| Time | Beat | Console action | Stage on screen | Say (script) |
|---|---|---|---|---|
| 0:00–0:25 | Problem — named beneficiary | Console idle, repo visible | (none yet) | Five-engineer shop; small fixes cost a senior hour each and wait for weeks. |
| 0:25–0:35 | File the issue | Pick Tier 1, Mock/Live as rehearsed, start run | guardrail | "One issue in. Watch what happens with no human touching it." |
| 0:35–1:35 | Agents work | Let the timeline fill; narrate per stage, do not click ahead | triage → plan → code → tests → review | Triage states what "fixed" means; planner commits to scope; coder works on a branch; reviewer runs the suite and checks the diff. |
| 1:35–2:00 | Payoff | Open the Result stage / PR body (or the real PR in Live+PR mode) | done | "One issue in — one reviewed, tested pull request out." Tests green, diff limited to plan scope. |
| 2:00–2:35 | Trust beat | "Try to break it": submit the guardrail issue text | guardrail (blocked) | Agents stop and escalate with the approval handoff. "That's what makes this a service a business can trust." |
| 2:35–3:00 | Close | Switch to the eval scorecard tab | — | "Every run is scored — tests green, PR opened, nothing unrelated touched. DevOps as a Service: your backlog, handled — with receipts." |

Timing discipline: if the agents-work beat passes 1:35 without the
review stage completing, do not wait on camera — switch to
Fallback 1 and keep narrating the same beats.

## Fallbacks (decision thresholds, not vibes)

| # | Trigger | Cut to | Label on camera |
|---|---|---|---|
| 1 | A stage stalls >30s or a run errors | The backup take recorded the same day; if unusable, walk `demo-fallbacks/live/tier1-pr16/pr_body.md` + `demo-fallbacks/live/tier1-pr16/diff.patch` | Live capture — a real run's output (PR #16) |
| 2 | PR step fails but the fix is correct | The branch, the green counts in `demo-fallbacks/mock/tier1/result.json` (or the live 6 → 8), open the PR manually | Say plainly that the PR was opened manually |
| 3 | Total live failure | Walk in script order: `demo-fallbacks/live/tier1-pr16/`, then `demo-fallbacks/mock/guardrail/escalation.md` + `demo-fallbacks/mock/guardrail/approval_request.json`, then `demo-fallbacks/mock/manifest.json` for the eval story | Mock artifacts are labeled MOCK; the guardrail logic is deterministic and mode-identical |

Full fallback map and regeneration: `demo-fallbacks/README.md`
(mock half regenerates deterministically via
`generate_demo_fallbacks.py`; the live half is never regenerated).

## Rehearsal log (fill on Nov 2 — two takes required)

| Take | Date/time | Mode | Total time | Beats inside envelope? | Fallback used? | Usable? |
|---|---|---|---|---|---|---|
| Rehearsal (mock) |  | Mock |  |  |  |  |
| Take 1 (primary) |  |  |  |  |  |  |
| Take 2 (backup) |  |  |  |  |  |  |

A take counts as usable only if: total 2:30–3:00, all seven stages
(or their fallback artifacts) appear in order, the trust beat shows
the approval handoff, and no mock artifact is presented as live.
