# Generalization run 2 — a third codebase the pipeline had never seen

Maximizer iteration 19, Oct 25, 2026 (item-4 polish: new evidence, not
re-presentation). Machine-readable record: `generalization2-runs.json`
next to this file. Runner:
`hackathon-agent-scaffold/run_generalization2_eval.py`.

## Why

Iteration 15 replaced the seeded-repo-only assumption with one live
pass on an unseen codebase (ledgerlite) — but that left generalization
at n=1 synthetic issue on a package written for the evaluation. This
run adds a second, independent data point on a third codebase that
differs from both predecessors, so the generalization claim rests on
two unseen codebases, two domains, and two bug shapes.

## The target

`generalization2/` vendors **textkit**, a small stdlib-only Python
package created for this run and never previously run through the
pipeline. It differs from both earlier codebases:

- package name `textkit/` vs the demo repo's `app/` and ledgerlite
- domain: text normalization, tokens, slugs, and reading statistics
  vs pagination/HTTP/CLI reports and ledger cent amounts
- module layout: `normalize` / `tokens` / `slug` / `counts` vs
  `pagination` / `http_client` / `cli` / `report` and
  `amounts` / `entries` / `stats` / `report`
- baseline suite 10 tests (demo repo baseline: 6, ledgerlite: 9)
- no MockClient canned response exists for this issue — live-only

Its genuine pre-existing bug: `first_words()` in `textkit/tokens.py`
sliced `words[: n + 1]` instead of `words[:n]`, returning one word
more than requested and contradicting its own docstring. Baseline
repro: `first_words('alpha beta gamma delta', 2)` returned
'alpha beta gamma', expected 'alpha beta'. The baseline suite passed
10/10 with the bug present (the exact-count case was uncovered). The
vendored copy was not tuned after the run — the pipeline ran against
a fresh git-initialized copy, and the vendored copy still reproduces
the bug in place.

The issue: "Fix first_words returning one word too many"
(`generalization2/issue.json`).

## The measured live run (connector, kept split config)

Run at 2026-10-25T22:56:32Z through the custom.meta-model-api
connector (no env key), CODER/REVIEWER on muse-wonder-1.0 and
TRIAGE/PLANNER on muse-spark-1.3 — the entry's kept live
configuration, recorded per call in `generalization2-runs.json`.

| | |
|---|---|
| Outcome | **passed** |
| Tests | 10 → 15 discovered (+5) |
| Wall clock | 31.98s |
| Model calls | 4 (one per role) |
| Est. API cost | $0.0144 (char estimate, see COST_ACCOUNTING.md) |
| Reviewer | approve |
| Files touched | `textkit/tokens.py`, `tests/test_tokens_regression.py` |
| Unexpected files | none |

The fix is one expression — `words[:n]` — and the coder added a new
regression file with five tests: exact count, n=1, n equal to the
word count, non-positive n, and fewer words than n (plus empty text).
The planner located the bug's module from an unseen file tree and
named the new regression file per the prompt convention.

## What this does and does not prove

Combined with iteration 15, the pipeline has now passed live, end to
end, on two codebases it had never seen, in two different domains,
with two different bug shapes (a wrong-branch return and an
off-by-one slice) — 9 → 13 in 37.73s and 10 → 15 in 31.98s. It does
NOT prove performance on a real team's codebase: both targets are
still small synthetic packages written for this evaluation (n=1
issue each, one run each), there are still no real users, and review
time remains the IMPACT_MODEL.md assumption. Those caps stand; the
single-generalization-sample cap does not.
