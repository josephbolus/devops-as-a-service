"""Dependency health check behind the /health endpoint.

Expansion seed issue #8 (health-check correctness, intentional — do
not fix in the scaffold): the endpoint reports healthy whenever ANY
check passes, so a dead critical dependency (the database) still
returns 200 and the load balancer keeps sending traffic to a service
that cannot serve it.
"""


def overall_status(checks):
    """'healthy' only if every critical check is ok.

    `checks` is a list of {"name": str, "ok": bool, "critical": bool}.
    A failing non-critical check degrades but does not unhealth the
    service; a failing critical check must make it 'unhealthy'.
    """
    # BUG: any single passing check marks the whole service healthy,
    # regardless of which critical dependencies are down.
    if any(c["ok"] for c in checks):
        return "healthy"
    return "unhealthy"


def http_status(checks):
    """HTTP status for /health: 200 when healthy, 503 when not."""
    return 200 if overall_status(checks) == "healthy" else 503
