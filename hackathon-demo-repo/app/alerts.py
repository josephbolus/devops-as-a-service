"""Alert rule evaluation.

Expansion seed issue #9 (alerting defect, intentional — do not fix in
the scaffold): the threshold comparison is inverted, so the rule pages
the on-call for healthy (low) values and stays silent while the real
metric is above the threshold during an incident.
"""


def should_page(metric, value, threshold):
    """Page when `value` rises ABOVE `threshold` for `metric`."""
    # BUG: '<' pages on low/healthy values and misses real breaches.
    return value < threshold


def describe_rule(metric, threshold):
    return f"page when {metric} > {threshold}"
