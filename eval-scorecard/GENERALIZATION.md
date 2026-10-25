# Generalization run — a second codebase the pipeline had never seen

Maximizer new-feature backlog item 1, Oct 25, 2026. Machine-readable
record: `generalization-runs.json` next to this file. Runner:
`hackathon-agent-scaffold/run_generalization_eval.py`.

## Why

Every live result before this run was on the seeded demo repo
(`hackathon-demo-repo/`) — the codebase the scaffold's issues, mock
responses, and prompts grew up with. Impact's evidence therefore
carried an untested assumption: that the results hold only there.
This run replaces that assumption with a measurement.

## The target

`generalization/` vendors **ledgerlite**, a small stdlib-only Python
package created for this run and never previously run through the
pipeline. It differs from the seeded demo repo in every surface way:

- package name `ledgerlite/` vs the demo repo's `app/`
- domain: ledger cent amounts and summary statistics vs pagination,
  HTTP retry, and CLI reports
- module layout: `amounts` / `entries` / `stats` / `report` vs
  `pagination` / `http_client` / `cli` / `report`
- baseline suite 9 tests (demo repo baseline: 6)
- no MockClient canned response exists for this issue — the live
  models had no scaffold-provided answer to replay

Its genuine pre-existing bug: `median_cents()` in
`ledgerlite/stats.py` returned the upper middle value for even-length
inputs instead of averaging the two middle values, contradicting its
own docstring. Baseline repro: `median_cents([100, 200, 300, 400])`
returned 300, expected 250. The baseline suite passed 9/9 with the
bug present (the even-count case was uncovered). The vendored copy
was not tuned after the run — the pipeline ran against a fresh
git-initialized copy, and the vendored copy still reproduces the bug
in place.

The issue: "Fix median_cents for even-length amount lists"
(`generalization/issue.json`).

## The measured live run (connector, kept split config)

Run at 2026-10-25T18:56:16Z through the custom.meta-model-api
connector (no env key), CODER/REVIEWER on muse-wonder-1.0 and
TRIAGE/PLANNER on muse-spark-1.3 — the entry's kept live
configuration, recorded per call in `generalization-runs.json`.

| | |
|---|---|
| Outcome | **passed** |
| Tests | 9 → 13 discovered (+4) |
| Wall clock | 37.73s |
| Model calls | 4 (one per role) |
| Reviewer | approve |
| Files touched | `ledgerlite/stats.py`, `tests/test_stats_regression.py` |
| Unexpected files | none |

The fix itself is one line — `return (ordered[mid - 1] +
ordered[mid]) / 2` — and the coder added a new regression file with
four tests: even-count averaging, unsorted input, a .5 half-value
result, and odd-count behavior unchanged. The planner named that new
file (`tests/test_stats_regression.py`, following the prompt's
`tests/test_<module>_regression.py` convention) rather than editing
the existing baseline file — a plan shape the seeded runs also used,
now produced for a module the scaffold had never named.

## What differed from the seeded repo

- **Baseline size:** 9 tests before, not 6 — the pipeline's
  test-growth coverage guard compared against the new codebase's own
  baseline, not a hard-coded one.
- **Discovery:** the planner had to locate the bug's module from a
  file tree it had never seen (`ledgerlite/stats.py` out of seven
  package/test files) and did so with no unexpected files.
- **No mock safety net:** MockClient has canned responses only for
  the three seeded issues; this run was live-only by construction.
- **Nothing else differed:** same guardrail-first order, same four
  role prompts and JSON schemas, same pass definition (tests green,
  reviewer approve, test count grows, no unexpected files) — that
  sameness is the point of the measurement.

## What this does and does not prove

It proves the pipeline — prompts, guardrail, context wiring
(repo tree, planned-file contents, diff), and pass criteria — works
end to end on a codebase whose package, domain, and layout it had
never seen, with a measured pass (9 → 13 in 37.73s), not an
assertion. It does NOT prove performance on a real team's codebase:
ledgerlite is still a small synthetic package written for this
evaluation (n=1 issue, one run), there are still no real users, and
review time remains the IMPACT_MODEL.md assumption. Those caps
stand; the seeded-repo-only cap does not.
