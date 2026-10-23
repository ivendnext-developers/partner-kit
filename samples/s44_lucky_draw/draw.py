"""S44 — *Lucky draw*: the pure core (no framework, no network), shared by the service and its tests.

The shop's two Desk buttons on a campaign (the Desk action extension point, ``desk_action/1``) each send one signed POST
per press:

    {"point": "desk_action/1", "context": {"v": 1, "action", "label", "user", "lang",
                                           "records": [{"doctype": "PP LDW Campaign", "name", "fields": {"name"}}],
                                           "inputs": {}, "idempotency_key"}}

``verify`` checks the signature the shop puts on every call; ``campaign_of`` takes the press's one campaign;
``rules_of`` reads the campaign's own rule (dates, spend per entry, winners, reserves); ``entries_of`` counts each
qualifying till sale's entries, net of its returns; ``draw`` picks the winners and reserves, one prize per customer,
each entry with the same chance; ``fingerprint`` names the entry list so a later count can prove it was the same; the
``*_answer`` functions build the reply in the extension point's closed vocabulary. ⛔ The answer never writes anything:
the service writes the campaign itself, with its own API key and its own rights, BEFORE it answers.
"""

from __future__ import annotations

import base64
import bisect
import datetime
import hashlib
import hmac
import time
from decimal import ROUND_FLOOR, Decimal, InvalidOperation

PREFIX = "PP LDW"
CAMPAIGN = "PP LDW Campaign"
SKEW_S = 300             # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
MOST_WINNERS, MOST_RESERVES = 50, 20
DRAWN = "Drawn"


def use_prefix(prefix: str):
    """The record type under another prefix: *IVENDNEXT LDW Campaign* for the library's app."""
    global PREFIX, CAMPAIGN
    PREFIX, CAMPAIGN = prefix, f"{prefix} Campaign"


def verify(timestamp: str | None, signature: str | None, raw: bytes, secret: str, now: float | None = None) -> str:
    """``""`` when the request is the shop's, else why not. The signature is base64 HMAC-SHA256 of
    ``<timestamp>.<raw body>`` with the subscription's secret (the installer handed it back once)."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit()) or abs((now or time.time()) - int(ts)) > SKEW_S:
        return "the request's time is missing or too far from ours"
    want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
    if not hmac.compare_digest(want, sig.encode()):
        return "the signature does not match"
    return ""


def campaign_of(body: dict) -> tuple[str, str]:
    """(the campaign's name, the pressing user), or ``ValueError`` — checked before anything is read or written."""
    if not isinstance(body, dict) or body.get("point") != "desk_action/1":
        raise ValueError("not a desk_action/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or not isinstance(ctx.get("records"), list):
        raise ValueError("no records")
    if len(ctx["records"]) != 1:
        raise ValueError("one campaign a press")
    rec = ctx["records"][0]
    if not isinstance(rec, dict) or rec.get("doctype") != CAMPAIGN or not isinstance(rec.get("name"), str) \
            or not rec["name"]:
        raise ValueError("not a campaign")
    user = ctx.get("user")
    return rec["name"], user if isinstance(user, str) else ""


def date_of(v) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _money(v) -> Decimal | None:
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return None
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def _whole(v, default: int = 0) -> int | None:
    """A whole number the shop typed (blank: the default), or None when it is not one."""
    if v is None or v == "":
        return default
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def today_at(hours, now: float | None = None) -> datetime.date:
    """The shop's own day: UTC moved by the campaign's hours from UTC (blank: UTC)."""
    t = datetime.datetime.fromtimestamp(now if now is not None else time.time(), datetime.timezone.utc)
    return (t + datetime.timedelta(hours=hours if isinstance(hours, (int, float)) and not isinstance(hours, bool)
                                   else 0)).date()


class Rules:
    def __init__(self, company, start, end, spend, most, winners, reserves, tills, groups):
        self.company, self.start, self.end, self.spend, self.most = company, start, end, spend, most
        self.winners, self.reserves, self.tills, self.groups = winners, reserves, tills, groups


def rules_of(c: dict) -> Rules | str:
    """The campaign's rule, or the sentence that says what to fix (shown to the manager)."""
    start, end = date_of(c.get("from_date")), date_of(c.get("to_date"))
    if not c.get("company") or not start or not end:
        return "Fill the campaign's company and its first and last days, then press again."
    if end < start:
        return "The campaign's last day is before its first. Fix the dates, then press again."
    spend = _money(c.get("spend_per_entry"))
    if spend is None or spend <= 0:
        return "Fill the spend for one entry (such as 200), then press again."
    most, winners, reserves = _whole(c.get("most_entries_per_sale")), _whole(c.get("winners"), 1), \
        _whole(c.get("reserves"))
    if most is None or most < 0:
        return "Most entries per sale is a whole number, or 0 for no limit."
    if winners is None or not 1 <= winners <= MOST_WINNERS:
        return f"Winners is a whole number from 1 to {MOST_WINNERS}."
    if reserves is None or not 0 <= reserves <= MOST_RESERVES:
        return f"Reserves is a whole number from 0 to {MOST_RESERVES}."
    tills = sorted({r.get("pos_profile") for r in c.get("tills") or [] if isinstance(r, dict) and r.get("pos_profile")})
    groups = sorted({r.get("customer_group") for r in c.get("customer_groups") or []
                     if isinstance(r, dict) and r.get("customer_group")})
    return Rules(c["company"], start, end, spend, most, winners, reserves, tills, groups)


def groups_under(tree: list[dict], chosen: list[str]) -> set[str]:
    """The chosen customer groups and every group below one of them (the tree's lft and rgt)."""
    spans = [(g.get("lft"), g.get("rgt")) for g in tree if isinstance(g, dict) and g.get("name") in chosen]
    spans = [(l, r) for l, r in spans if isinstance(l, int) and isinstance(r, int)]
    out = set(chosen)
    for g in tree:
        if isinstance(g, dict) and isinstance(g.get("lft"), int) and any(l <= g["lft"] and g["rgt"] <= r
                                                                         for l, r in spans):
            out.add(g["name"])
    return out


def entries_of(sales: list[dict], returns: list[dict], walk_ins: set[str], rules: Rules,
               groups: set[str] | None) -> list[tuple[str, str, int]]:
    """Each qualifying sale's ``(sale, customer, entries)``, in sale order (date, time, name). A sale qualifies when it is
    inside the campaign's days, on one of its tills (all when none is listed), by a named customer (never a till's
    walk-in customer), in one of its groups or below one (all when none is listed). Its entries are its net total in the
    company's currency (less every return against it) divided by the spend for one entry, rounded down, at most the
    campaign's most per sale. A sale with no whole entry is left out."""
    back: dict[str, Decimal] = {}
    for r in returns:
        amount = _money(r.get("base_grand_total")) if isinstance(r, dict) else None
        if amount is not None and r.get("return_against"):
            back[r["return_against"]] = back.get(r["return_against"], Decimal(0)) + amount
    out = []
    for s in sales:
        if not isinstance(s, dict) or not s.get("name"):
            continue
        customer, day = s.get("customer"), date_of(s.get("posting_date"))
        if not customer or customer in walk_ins or not day or not rules.start <= day <= rules.end:
            continue
        if rules.tills and s.get("pos_profile") not in rules.tills:
            continue
        if groups is not None and s.get("customer_group") not in groups:
            continue
        total = _money(s.get("base_grand_total"))
        if total is None:
            continue
        n = int(((total + back.get(s["name"], Decimal(0))) / rules.spend).to_integral_value(rounding=ROUND_FLOOR))
        if rules.most:
            n = min(n, rules.most)
        if n > 0:
            out.append((str(day), str(s.get("posting_time") or ""), s["name"], customer, n))
    out.sort()
    return [(name, customer, n) for _, _, name, customer, n in out]


def fingerprint(entries: list[tuple[str, str, int]]) -> str:
    """SHA-256 of the entry list, one ``sale<TAB>customer<TAB>entries`` line each, in order: the same sales, counted
    again, give the same fingerprint."""
    return hashlib.sha256("\n".join(f"{s}\t{c}\t{n}" for s, c, n in entries).encode()).hexdigest()


def draw(entries: list[tuple[str, str, int]], places: int, randbelow) -> list[dict]:
    """``places`` customers, each drawn once, in drawn order. Entries are numbered 1, 2, 3 … through the list; each draw
    picks one of the entries still in the pool, every one with the same chance (``randbelow(n)``: a whole number from 0
    to n-1, the service's cryptographic source), and its customer's every entry then leaves the pool. Each place names
    the drawn entry by its number in the whole list, its sale, and the customer's entries."""
    first, total = [], {}
    k = 1
    for sale, customer, n in entries:
        first.append(k)
        k += n
        total[customer] = total.get(customer, 0) + n
    pool = list(range(len(entries)))
    out = []
    while pool and len(out) < places:
        ends, at = [], 0
        for i in pool:
            at += entries[i][2]
            ends.append(at)
        r = randbelow(at)                                    # 0 … at-1: one entry of the pool
        j = bisect.bisect_right(ends, r)
        i = pool[j]
        sale, customer, _ = entries[i]
        number = first[i] + r - (ends[j - 1] if j else 0)
        out.append({"customer": customer, "entries": total[customer], "entry_no": number, "sale": sale})
        pool = [p for p in pool if entries[p][1] != customer]
    return out


def results_of(places: list[dict], winners: int) -> list[dict]:
    """The results table's rows: ranks from 1, the first ``winners`` places winners, the rest reserves."""
    return [dict(p, rank=i + 1, kind="Winner" if i < winners else "Reserve") for i, p in enumerate(places)]


def _fit(text: str, most: int = 280) -> str:
    return text if len(text) <= most else text[: most - 1] + "…"


def _n(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def _stats(entries) -> tuple[int, int, int]:
    return len(entries), len({c for _, c, _ in entries}), sum(n for _, _, n in entries)


def message(body: str, level: str = "success", refresh: bool = False, title: str = "Lucky draw") -> dict:
    out = {"message": {"title": title, "body": _fit(body), "level": level}}
    if refresh:
        out["refresh"] = True
    return out


def count_answer(entries) -> dict:
    sales, customers, n = _stats(entries)
    if not n:
        return message("No entries yet: no sale in the campaign's days, tills and customer groups reaches the spend for "
                       "one entry. A sale on a till's walk-in customer is never an entry.", "info", refresh=True)
    return message(f"{_n(sales, 'sale', 'sales')} by {_n(customers, 'customer', 'customers')}: "
                   f"{_n(n, 'entry', 'entries')} so far.", refresh=True)


def draw_answer(results: list[dict], winners: int, reserves: int, entries) -> dict:
    n = _stats(entries)[2]
    got_w = sum(1 for r in results if r["kind"] == "Winner")
    got_r = len(results) - got_w
    body = f"Drew {_n(got_w, 'winner', 'winners')}"
    body += f" and {_n(got_r, 'reserve', 'reserves')}" if got_r else ""
    body += f" from {_n(n, 'entry', 'entries')}."
    if got_w + got_r < winners + reserves:
        body += f" Only {_n(len(results), 'customer has', 'customers have')} entries, so every one was drawn."
    return message(body + " The results are on the campaign.", refresh=True)


def already_answer(drawn_on, drawn_by) -> dict:
    when = str(drawn_on or "")[:20] or "an earlier press"
    who = f" by {drawn_by}" if drawn_by else ""
    return message(f"Already drawn on {when}{who}. A draw is never repeated.", "warning", refresh=True)
