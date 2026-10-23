"""A small status report — the data the CLI prints.

Tier-3 seed issue: add a `--json` flag that emits this same report as
JSON on stdout; human output stays the default.
"""

REPORT = {
    "service": "demo-api",
    "status": "healthy",
    "checks": [
        {"name": "database", "ok": True, "latency_ms": 12},
        {"name": "cache", "ok": True, "latency_ms": 3},
        {"name": "queue", "ok": False, "latency_ms": 0},
    ],
}


def human_report(report=REPORT):
    lines = [f"Service: {report['service']}  Status: {report['status']}"]
    for c in report["checks"]:
        mark = "OK  " if c["ok"] else "FAIL"
        lines.append(f"  [{mark}] {c['name']}: {c['latency_ms']} ms")
    return "\n".join(lines)
