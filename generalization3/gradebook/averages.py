"""Score averaging helpers."""


def simple_mean(scores):
    """Arithmetic mean of `scores`; an empty sequence gives 0.0."""
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def weighted_mean(values, weights):
    """Weighted mean: sum(v * w for v, w in zip(values, weights))
    divided by the sum of the weights.

    `values` and `weights` have equal length. An empty input, or a
    total weight of zero, gives 0.0.
    """
    if not values:
        return 0.0
    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights)) / len(values)  # BUG: must divide by total_weight, not len(values)
