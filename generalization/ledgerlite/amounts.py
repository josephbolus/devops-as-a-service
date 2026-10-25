"""Money amounts as integer cents: parsing and formatting."""


def parse_cents(text):
    """Parse a dollar string like '12.34' or '-3.05' into integer cents."""
    s = text.strip()
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    if "." in s:
        dollars, frac = s.split(".", 1)
        frac = (frac + "00")[:2]
    else:
        dollars, frac = s, "00"
    cents = int(dollars or "0") * 100 + int(frac)
    return -cents if neg else cents


def format_cents(cents):
    """Format integer cents as a dollar string, e.g. 1234 -> '12.34'."""
    sign = "-" if cents < 0 else ""
    cents = abs(int(cents))
    return f"{sign}{cents // 100}.{cents % 100:02d}"
