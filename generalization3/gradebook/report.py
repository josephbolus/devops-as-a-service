"""End-to-end grade reporting: combines averages and letters."""
from .averages import weighted_mean
from .letters import letter_grade


def final_letter(values, weights):
    """Letter grade for the weighted mean of `values`/`weights`."""
    return letter_grade(weighted_mean(values, weights))


def summarize(values, weights):
    """{'mean': weighted mean, 'letter': its letter grade}."""
    mean = weighted_mean(values, weights)
    return {"mean": mean, "letter": letter_grade(mean)}
