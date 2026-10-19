"""S3 outside — the pure core: which lines of a booked sale were charged below list by more than the threshold.

COPIED FROM the embedded version's pure core (``deviation_percent``, ``deviations``; that version is kept
internal) @ commit 491087b, unchanged. A defect here is a defect there: fix both, and report it with a Kit defect
issue.
"""


def _f(x) -> float:
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def deviation_percent(price_list_rate, charged_rate) -> float:
    plr, rate = _f(price_list_rate), _f(charged_rate)
    if plr <= 0 or rate >= plr:
        return 0.0
    return round((plr - rate) / plr * 100.0, 4)


def deviations(lines: list, threshold: float) -> list:
    out = []
    for line in lines or []:
        pct = deviation_percent(line.get("price_list_rate"), line.get("rate"))
        if pct > _f(threshold):
            out.append({**line, "deviation_percent": pct})
    return out
