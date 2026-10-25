# DevOps as a Service

A multi-agent GitHub Issue workflow: **one issue in → a fix → a tested pull
request out** — and when an issue is destructive or ambiguous, the agents
stop and escalate to a human instead.

Built for the **Meta Global AI Developer Hackathon 2026** (Indie Dev Track),
sprint window **Oct 26 – Nov 4, 2026**. Entry as submitted: *"DevOps as a
Service"*, showcasing the multi-agent workflow that checks out the code,
performs the fix, then opens a PR.

## Who this is for

Small engineering teams — two to ten developers, like the five-engineer
shop in the demo — whose backlog is full of small, well-defined fixes.
Each one costs a senior engineer an hour or more of focused time, so the
small stuff waits for weeks while the expensive people are the bottleneck.

DevOps as a Service clears that backlog: file the issue, and the agents
return a reviewed, tested pull request. The team's lead spends minutes
approving instead of hours implementing — and every run is scored (see
the eval scorecard in `hackathon-demo-repo/`), so the value is measured,
not asserted. Destructive or ambiguous issues are never auto-fixed; they
come back as a written escalation for a human decision.

Path to real use: point the workflow at any GitHub repository. After the
hackathon it becomes a managed service — the same loop, run for client
teams that don't have DevOps hours to spare.

## How it works

1. **Triage agent** reads the issue and restates the problem + acceptance criteria.
2. **Planner agent** breaks the fix into steps and names the files it expects to touch.
3. **Coder agent** checks out a branch, implements the fix, adds/updates tests.
4. **Reviewer agent** runs the test suite and inspects the diff for unrelated changes.
5. **PR step** opens a pull request with a summary of what changed and what was checked.

A **deterministic guardrail** runs before any model call: destructive or
ambiguous issues are escalated with a written risk summary, never auto-fixed.
Model calls go through one `llm` abstraction pointed at the Meta Model API.

## Layout

| Path | What it is |
|---|---|
| `hackathon-demo-repo/` | The demo codebase the agents work on — intentionally unfinished in exactly three places (Tier-1 pagination bug, Tier-2 retry, Tier-3 `--json`). See its README for the eval scorecard. |
| `hackathon-agent-scaffold/` | The agent-loop pipeline (`daas/` package: guardrail, llm abstraction, pipeline), seeded issue definitions, and a demo runner. See its README for design notes. |
| `demo-fallbacks/` | Recording-day end states for the demo: mock Tier 1/2/3 + guardrail artifacts and the captured live Tier-1 PR (#16). See its README for the fallback map. |

## Run the baselines

```bash
cd hackathon-demo-repo && python3 -m unittest discover -s tests -q   # 6 passing; the Tier-1 bug is not yet covered by a test
cd ../hackathon-agent-scaffold && python3 -m unittest discover -s tests -q  # pipeline end-to-end + guardrail tests
python3 run_demo.py --repo ../hackathon-demo-repo --issue issues/tier1.json --mock --out /tmp/daas-out
```

No dependencies beyond the Python 3 standard library (mock mode). Real runs
use the Meta Model API via `MODEL_API_KEY` / `META_API_KEY`.

## Sprint

Day-by-day plan (Oct 26 – Nov 4) is tracked in this repo's **milestones and
issues**: agent loop → eval gate + published scorecard → guardrails + human
approval → demo video + submission (due Nov 4, 9:00 PM ET).

## Separations

- No Meridian Runtime code in this repo (cleanroom).
- No RAG prototype code — this is the submitted DevOps entry only.
