# Approve-to-Pay

**Your agents can buy — with receipts, and only with your approval.**

Approve-to-Pay is an agentic purchasing flow built on the
[DevOps as a Service](../README.md) guardrail pattern, pointed at money
instead of code. An agent is given purchasing jobs; a **deterministic
guardrail** checks each one in pure code; the survivors become real
**PayPal Orders API** orders that sit **UNCAPTURED** until a human
approver authorizes the exact spend. Agents propose — humans authorize.
Every decision lands in an append-only log, so a blocked purchase's
"$0 moved" is auditable, not narrated.

Built for the **PayPal AI Hackathon** (Nov 10–12, 2026), targeting
*Best Use of PayPal + AI* and *Best Use of Agentic Commerce*.

## How it works

For each purchasing job, in order:

1. **Guardrail (pure code, no model judgment)** — category allowlist,
   budget cap, and price-drift check (checkout price must equal the
   quoted price). A blocked job stops here: **no order is created**.
2. **Create order** — PayPal Orders API v2, intent `CAPTURE`. The order
   exists, UNCAPTURED.
3. **Payer approval** — PayPal's own step: the payer approves on
   PayPal's page (the `payer-action` link). Distinct from our gate.
4. **Console approval** — Approve-to-Pay's human gate. The approver sees
   the exact item and amount. **"No" ⇒ capture is never called** and
   the order stays uncaptured.
5. **Capture** — only on guardrail pass + payer approval + console
   approval. Returns `COMPLETED`; the captured order is the receipt.

## The frozen task set

`tasks.json` is a **frozen set of 20 purchasing jobs**, defined before
the runner was wired and pinned by `tasks.sha256` (the runner refuses
to run a modified set): 8 in-budget, 4 over-budget, 3 disallowed
category, 3 price-changed-between-quote-and-checkout, 2 approver-says-no.
Each job carries its expected outcome. The runner reports the actual
counts — captured, blocked by guardrail (by reason), blocked by
approver — **and the misses**: false blocks and missed blocks. Only
measured numbers; no modeled savings.

## Run it

Zero dependencies — Python 3.10+ standard library only.

```bash
cd approve-to-pay

# Tests (guardrail, the never-capture-on-no invariant, task-set integrity)
python3 -m unittest discover -s tests -v

# Run the frozen task set (appends to decision-log.jsonl, writes
# results/latest-report.md and prints the same report)
python3 run_tasks.py

# Run one job
python3 run_tasks.py --job ATP-019
```

### PayPal sandbox (live mode)

Without credentials the client runs in **clearly-labeled mock mode**
against recorded Orders API fixtures (`fixtures/mock_orders.json`), so
the full pipeline is testable as-is. For the real PayPal sandbox, get a
sandbox app's credentials from the PayPal Developer Dashboard and:

```bash
export PAYPAL_CLIENT_ID=<your sandbox client id>
export PAYPAL_CLIENT_SECRET=<your sandbox secret>
# export PAYPAL_ENV=live   # only for the production API; default sandbox
python3 run_tasks.py
```

Credentials are read from the environment only — never hardcoded,
never committed (`.env` is gitignored; see `.env.example`).

## The decision log

`decision-log.jsonl` is append-only: one JSON line per job run with the
timestamp, run id, PayPal order id, guardrail verdict + reason, payer
approval, approver decision, and whether capture was called. For any
blocked purchase you can verify from the log itself that
`capture_called` is `false` — that is the "$0 moved" evidence.

## Layout

```
tasks.json / tasks.sha256   the frozen 20-job set + its checksum
approvetopay/
  guardrail.py              deterministic verdicts (budget/category/drift)
  paypal_client.py          Orders API client (live) + fixture mock
  pipeline.py               guardrail -> order -> payer approval ->
                            console approval -> capture (or never)
  decision_log.py           append-only JSONL audit trail
  cli.py                    runner + report (counts incl. the misses)
fixtures/mock_orders.json   recorded-shape Orders API responses
tests/                      guardrail, invariant, and task-set tests
results/                    latest run report (md + json)
decision-log.jsonl          the append-only audit trail itself
```

## AI tools used

- **Muse (Meta's AI agent, Muse Wonder)** — designed and built this
  module, including the guardrail, pipeline, task set and tests.
- The verdict path deliberately uses **no LLM**: guardrail decisions
  are deterministic code, so the same job always gets the same verdict
  and every block has a machine-checkable reason. The planner/shopper
  agent pattern is inherited from DevOps as a Service (Meta Model API,
  Muse Spark) — in Approve-to-Pay the agents propose purchasing jobs;
  authorization stays with code and the human gate.

## License

MIT — see the repository root [LICENSE](../LICENSE).
