# Demo fallback package — recording-day end states

The demo script (Nov 2 recording) has three fallbacks. This package is
the artifact each fallback points at, so no fallback depends on memory,
a live network, or re-running anything under pressure. Everything here
was generated and verified on Oct 25, 2026, and is pinned by
`hackathon-agent-scaffold/tests/test_demo_fallbacks.py`.

## What's here

| Path | What it is | Honesty label |
|---|---|---|
| `live/tier1-pr16/` | End state of a **real** run: Meta Model API (via the secure connector) → triage/planner/coder/reviewer → branch → PR #16 opened. `pr_body.md` and `diff.patch` are captured verbatim from GitHub; `pr.json` + `PROVENANCE.md` record the source. Tests 6 → 8 discovered, reviewer approved, diff limited to the two planned files. | LIVE |
| `mock/tier1/`, `mock/tier2/`, `mock/tier3/` | MockClient end states for all three eval tiers: `pr_body.md`, `result.json` (passed, test counts 6→7 / 6→9 / 6→8, no unexpected files), and `diff.patch` vs the pristine demo repo. | MOCK — say so if shown |
| `mock/guardrail/` | Mock guardrail end state: `escalation.md` (structured human approval request: no PR opened, what the pipeline did NOT do, three human options, blank decision record) + `approval_request.json` (the same request, machine-readable) + `result.json` with the escalation reason. | MOCK — the escalation logic is deterministic code, identical in live mode |
| `mock/manifest.json` | Machine-readable summary of the four mock runs. | — |

Regenerate the mock half (never touches `live/`):

```bash
cd hackathon-agent-scaffold && python3 generate_demo_fallbacks.py
```

## Which fallback uses what (per the demo script)

1. **Agent run stalls or errors** → cut to the backup take. If the
   backup take is also unusable, walk `live/tier1-pr16/pr_body.md` on
   screen — it is a real run's output, not a reconstruction.
2. **PR step fails but the fix is correct** → show the branch, the
   green test counts in `mock/tier1/result.json` (or the live PR's
   6 → 8), and open the PR manually on camera, saying so plainly.
3. **Total live failure** → walk the pre-recorded end state in script
   order: live Tier-1 PR body + diff (`live/tier1-pr16/`), then the
   guardrail escalation (`mock/guardrail/escalation.md` — narrate it
   as the deterministic guardrail's output, which is mode-independent),
   then the eval story from `mock/manifest.json` (three tiers pass,
   no unexpected files). Label the mock artifacts as mock on camera;
   the live PR needs no label beyond what it is.

## Rehearsal checklist (do once before Nov 2)

- [ ] Open every file above once at 125% browser zoom — diff text readable.
- [ ] Time the fallback-3 walkthrough against the script: it must fit
      the same 2:30–3:00 envelope (the beats are identical, only the
      visuals change).
- [ ] Confirm PR #16's state in `live/tier1-pr16/PROVENANCE.md` still
      matches GitHub; if it was merged or closed, update the capture
      (`gh pr view 16`, `gh pr diff 16`) and the provenance note.
