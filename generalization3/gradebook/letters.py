"""Letter grades and grade points."""


def letter_grade(score):
    """Letter for a numeric score: 90 or above is an A, 80 or above
    a B, 70 or above a C, 60 or above a D, anything below an F."""
    if score > 90:  # BUG: 90 exactly must be an A (>= 90), not a B
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def grade_points(letter):
    """Grade points for a letter: A=4, B=3, C=2, D=1, F=0."""
    return {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}[letter]
