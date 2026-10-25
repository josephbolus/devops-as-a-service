# Impact model — DevOps as a Service

A worked model of the time saving for the team this entry is built
for. Pinned by `hackathon-agent-scaffold/tests/test_impact_model.py`,
which recomputes every number in the tables below from the stated
inputs.

**This is a model, not a measured result.** No real users yet. The
measured runs behind it are the live eval record (PR #16 first, then
the timed 3/3 live eval in `eval-scorecard/`). Every input below
is labeled **measured**, **entry assertion**, or **model
assumption** — and the last section says exactly how each assumption
gets replaced by a measurement. No dollar saving is claimed for
labour: no wage rate has been measured, so the labour side of this
model stays in hours. The per-run API cost, by contrast, has now
been measured (as a labeled estimate) — see the cost section below.

## Who the model is about

The five-engineer shop named in the README ("Who this is for") and
the demo opening: a small team whose backlog is full of small,
well-defined fixes, each one waiting because a senior engineer is
the bottleneck. The model applies **only** to that class of issue —
small and well-defined, passing the deterministic guardrail, and
meeting the eval pass definition (tests green, PR produced, no
files touched outside the planner's expected set, per
`eval-scorecard/SCORECARD.md`). Escalated issues are excluded: the
guardrail returns those to a human, and no saving is claimed for
them.

## Inputs (every one labeled)

| Input | Value used | Kind | Source / note |
|---|---|---|---|
| Team shape | five-engineer shop | entry assertion | README "Who this is for"; demo opening |
| Manual time per small fix | 60 min | entry assertion, used as a floor | README: "an hour or more of focused time" — the model uses exactly 60, so if the real figure is higher, the saving is larger |
| Lead review time per agent PR | 10 min | model assumption | README claims "minutes approving instead of hours implementing"; 10 is the assumption to be measured (sensitivity below) |
| Small-issue volume (B) | 3 / 5 / 10 per week | model assumption | No backlog has been audited yet; shown as a grid, not a point |
| Proof the loop produces a reviewable PR | PR #16: tests 6 → 8, reviewer approve, files inside plan scope | measured (n=1 live) | `eval-scorecard/SCORECARD.md`, live section |

## The arithmetic

Saved per passed issue = manual time − review time
= 60 min − 10 min = **50 min**.

Weekly saving = B × 50 min. A "month" below is 4 weeks; a year is
52 weeks.

| B (issues/week) | Saved per issue | Saved per week | Saved per 4 weeks | Saved per year |
|---|---|---|---|---|
| 3 | 50 min | 2.50 h | 10.0 h | 130.0 h |
| 5 | 50 min | 4.17 h | 16.7 h | 216.7 h |
| 10 | 50 min | 8.33 h | 33.3 h | 433.3 h |

Reading for the named beneficiary at the middle volume: a
five-engineer shop filing 5 small issues a week gets back 4.17
senior hours a week — about a tenth of one senior engineer's
40-hour week, every week, spent on work only they can do instead
of on fixes that waited weeks in the backlog.

## Sensitivity: what if review takes longer?

The 10-minute review is an assumption, so here is the same model at
B = 5 with slower reviews. The break-even is 60 min: any review
faster than doing the fix by hand still saves time.

| Review time | Saved per issue | Saved per week (B = 5) |
|---|---|---|
| 5 min | 55 min | 4.58 h |
| 10 min | 50 min | 4.17 h |
| 20 min | 40 min | 3.33 h |
| 30 min | 30 min | 2.50 h |

## Per-run API cost (measured estimate, Oct 25, 2026)

The API-cost input this model used to list as unmeasured is now
measured — as an estimate, labeled as one everywhere it appears.
Token usage is not exposed on the connector path (the helper
returns only the parsed reply), so the pipeline prices
character-count token estimates at the published rates; the full
record is `eval-scorecard/COST_ACCOUNTING.md` +
`eval-scorecard/cost-runs.json`, from live split-config runs that
passed 3/3 seeded tiers:

- **Est. API cost per passed issue: $0.0254.**
- Against this model's 50 min saved per passed issue, that is an
  **API cost per senior-hour saved of $0.0305** — three cents of API
  spend per hour of senior time the model says is returned. No wage
  rate is assumed for that ratio; it divides dollars actually
  (estimated-) spent by hours the model claims saved.
- The guardrail path costs $0.00 per escalation: it runs before any
  model call.

## What this model does NOT claim

- No dollar saving is claimed for labour (no wage rate measured;
  the API cost above is spend per fixed issue, not a labour saving).
- No wait-time reduction is quantified: the README's "waits for
  weeks" backlog delay is real framing, but turning it into a
  number needs queue data this model does not have.
- No pass-rate adjustment: the model is per **passed** issue. If
  the live pass rate is below 100%, the expected saving per
  submitted issue is lower, and failed runs may cost triage time —
  that cost is unmeasured, so it is named here, not hidden in the
  arithmetic.
- Mock runs contribute nothing to this model: they are plumbing
  proof, labeled as such in the eval scorecard, and are never
  counted as impact evidence.

## How to replace this model with measurements

1. **Time the review.** A team lead reviews a PR shaped like
   PR #16 with a timer, at least 5 reviews; the median replaces
   the 10-minute assumption.
2. **Audit a real backlog.** Count the small, well-defined issues
   filed by one real five-engineer team over 2 weeks; that count
   replaces the B grid with a point.
3. **Measure the live pass rate.** DONE Oct 25, ahead of the
   Days 3–4 slot: the timed live runs in
   `eval-scorecard/live-runs.json` passed 3/3 seeded tiers (plus a
   live guardrail escalation), so the measured seeded-set pass rate
   is 3/3 (n=3, one run each — not yet a backlog rate). No failed
   live run occurred, so failed-run triage time remains unmeasured.
4. **Measure the per-run API cost.** DONE Oct 25: live runs with
   pipeline cost capture are recorded in
   `eval-scorecard/cost-runs.json` (est. $0.0254 per passed issue,
   character-count estimates — API usage is not exposed on the
   connector path; see the cost section above). Replacing the
   estimate with provider-reported usage remains open for any
   transport that surfaces a `usage` field.
5. **Re-run this doc's tests.** `tests/test_impact_model.py`
   recomputes the tables from the inputs, so a changed input that
   is not carried through the arithmetic fails the suite.
