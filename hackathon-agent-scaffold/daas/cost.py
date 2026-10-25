"""Per-run cost accounting for the pipeline.

Why estimates, not API usage: the live path used for every measured
run is the custom.meta-model-api connector, and its helper
(`meta_api.py`, `chat_completion`) returns only the parsed reply
content — the API response envelope, including any `usage` field,
never reaches this process. The direct client (`MetaModelClient`)
likewise reads only `choices[0].message.content`. So per-role token
usage is NOT exposed to the pipeline today, and this module says so
wherever a number appears: token counts are ESTIMATES from character
counts (the standard ~4 chars/token heuristic), and dollar figures
are estimates computed from those estimates at the published
per-token prices below. If a future transport surfaces real `usage`,
`record_call` accepts it (`method="api_usage"`) and the summary
prefers it — nothing else changes.

Prices (USD per 1M tokens, standard/pay-as-you-go tier):
- muse-spark-1.3: $1.25 input / $4.25 output — verified 2026-10-23
  (connector doc for custom.meta-model-api).
- muse-wonder-1.0: $4.00 input / $20.00 output — Meta Model API
  published rates, cross-checked Oct 25, 2026.
- mock: $0 — MockClient makes no API call; its runs are plumbing
  proof and their zero cost is real, not an estimate.
"""
import json
import math

CHARS_PER_TOKEN = 4  # estimation heuristic, labeled wherever used

PRICES_USD_PER_MTOK = {
    "muse-spark-1.3": {"input": 1.25, "output": 4.25},
    "muse-wonder-1.0": {"input": 4.00, "output": 20.00},
    "mock": {"input": 0.0, "output": 0.0},
}

METHOD_API = "api_usage"
METHOD_ESTIMATE = "char_estimate"
METHOD_MOCK = "mock_no_api_call"

DISCLAIMER = (
    "Token counts are ESTIMATES from character counts "
    f"(~{CHARS_PER_TOKEN} chars/token): the connector path used for "
    "live runs does not expose API `usage` to the pipeline (the "
    "helper returns only the parsed reply). Dollar figures are "
    "estimates at the published per-token prices in daas/cost.py.")


def estimate_tokens(chars):
    """Estimated tokens for `chars` characters (ceil, min 0)."""
    if chars <= 0:
        return 0
    return int(math.ceil(chars / CHARS_PER_TOKEN))


def role_from_system(system):
    words = (system or "").strip().split()
    if not words:
        return "UNKNOWN"
    return "".join(ch for ch in words[0] if ch.isalnum()).upper() or "UNKNOWN"


def call_cost_usd(model, input_tokens, output_tokens):
    """USD cost of one call at the model's published prices.

    Unknown models are priced at the default model's rates and the
    caller is responsible for noting that; `record_call` records the
    model name verbatim so an unknown model is visible in the record.
    """
    price = PRICES_USD_PER_MTOK.get(model) or PRICES_USD_PER_MTOK["muse-spark-1.3"]
    return (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000


def record_call(role, model, system, user, response, usage=None):
    """One per-call cost record.

    `usage`, when a transport ever provides it, is
    {"prompt_tokens": int, "completion_tokens": int} from the API
    response and wins over the character estimate.
    """
    input_chars = len(system or "") + len(user or "")
    output_text = response if isinstance(response, str) else json.dumps(response)
    output_chars = len(output_text or "")
    if usage:
        input_tokens = int(usage.get("prompt_tokens", 0))
        output_tokens = int(usage.get("completion_tokens", 0))
        method = METHOD_API
    elif model == "mock":
        input_tokens = output_tokens = 0
        method = METHOD_MOCK
    else:
        input_tokens = estimate_tokens(input_chars)
        output_tokens = estimate_tokens(output_chars)
        method = METHOD_ESTIMATE
    return {
        "role": role,
        "model": model,
        "method": method,
        "input_chars": input_chars,
        "output_chars": output_chars,
        "input_tokens_est": input_tokens,
        "output_tokens_est": output_tokens,
        "cost_usd_est": round(call_cost_usd(model, input_tokens, output_tokens), 6),
    }


def summarize(calls):
    """Aggregate per-call records into a run cost summary.

    Shape (consumed by the pipeline result, the demo console results
    card, and the eval scorecard):
    {method, calls, input_tokens_est, output_tokens_est,
     total_usd_est, per_role: {ROLE: {calls, input_tokens_est,
     output_tokens_est, cost_usd_est, models}}, disclaimer}
    A run with no model calls (guardrail escalation) summarizes to
    zeroes with method "no_model_calls".
    """
    per_role = {}
    total_in = total_out = 0
    total_cost = 0.0
    methods = set()
    for c in calls or []:
        methods.add(c["method"])
        total_in += c["input_tokens_est"]
        total_out += c["output_tokens_est"]
        total_cost += c["cost_usd_est"]
        slot = per_role.setdefault(c["role"], {
            "calls": 0, "input_tokens_est": 0, "output_tokens_est": 0,
            "cost_usd_est": 0.0, "models": []})
        slot["calls"] += 1
        slot["input_tokens_est"] += c["input_tokens_est"]
        slot["output_tokens_est"] += c["output_tokens_est"]
        slot["cost_usd_est"] = round(slot["cost_usd_est"] + c["cost_usd_est"], 6)
        if c["model"] not in slot["models"]:
            slot["models"].append(c["model"])
    if not calls:
        method = "no_model_calls"
    elif methods == {METHOD_MOCK}:
        method = METHOD_MOCK
    elif METHOD_API in methods and len(methods) == 1:
        method = METHOD_API
    else:
        method = METHOD_ESTIMATE
    return {
        "method": method,
        "calls": len(calls or []),
        "input_tokens_est": total_in,
        "output_tokens_est": total_out,
        "total_usd_est": round(total_cost, 6),
        "per_role": per_role,
        "disclaimer": DISCLAIMER if method == METHOD_ESTIMATE else (
            "Mock run: no API call was made, so the cost is $0."
            if method == METHOD_MOCK else
            "No model calls were made (deterministic guardrail), so the cost is $0."
            if method == "no_model_calls" else
            "Token counts from API-reported usage."),
    }
