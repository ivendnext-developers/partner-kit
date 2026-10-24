"""S49 — *Post-sale feedback*: the pure core (no framework, no network), shared by the service and its tests.

The retailer's Desk button *Send feedback requests* on one or more rules (the Desk action extension point,
``desk_action/1``) sends one signed POST per press:

    {"point": "desk_action/1", "context": {"v": 1, "action", "label", "user", "lang", "idempotency_key", "inputs": {},
                                           "records": [{"doctype": "PP PSF Rule", "name", "fields": {"name"}}, …]}}

``verify`` checks the signature the retailer puts on every press; ``rules_of_press`` takes the pressed rules;
``rule_of`` reads one rule (its words, its days, its POS Profiles); ``choose`` picks, from a rule's recent till sales,
the ones to ask (one request per customer a press, never the walk-in customer, never a sale already asked, never a
customer who asked to stop, never a sale with no mobile number or e-mail); ``request_of`` builds the request the service
writes, with its signed ``link_of``; ``press_answer`` says what the press did. The customer's page calls carry the
link's ``s`` and ``t``: ``sale_of_token`` checks the signature before anything is read, ``page_of`` says what the page
shows and ``answer_of`` reads what the customer sent. ⛔ No answer writes anything: the service writes the requests
itself, with its own API key and its own rights, BEFORE it answers.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import re
import time
import urllib.parse

PREFIX = "PP PSF"
RULE, REQUEST = "PP PSF Rule", "PP PSF Request"
SKEW_S = 300                 # a press stamped further than this from our clock is refused (a replay window)
BODY_MAX = 256 * 1024
PAGE_BODY_MAX = 4096
MOST_RULES = 100             # the Desk action's own cap on ticked records
ANSWERS = ("Satisfied", "Neutral", "Not satisfied")   # stored in English, whatever words the customer was shown
COMMENT_MAX = 280
SIG_LEN = 22                 # 22 base64url characters: 132 bits of the HMAC
PHONE_CHARS = re.compile(r"[+(0-9][0-9 ()-]*")
EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s.]+(\.[^@\s.]+)+")
LOOK_BACK = (1, 7, 1)        # (least, most, blank) days back a press reaches
OPEN_DAYS = (1, 30, 7)       # days a link stays open after the sale
DEFAULT_QUESTION = "How was your visit today?"


def use_prefix(prefix: str):
    """The record types under another prefix: *IVENDNEXT PSF Rule* for the library's app."""
    global PREFIX, RULE, REQUEST
    PREFIX, RULE, REQUEST = prefix, f"{prefix} Rule", f"{prefix} Request"


def verify(timestamp: str | None, signature: str | None, raw: bytes, secret: str, now: float | None = None) -> str:
    """``""`` when the press is the retailer's, else why not. The signature is base64 HMAC-SHA256 of
    ``<timestamp>.<raw body>`` with the subscription's secret (the installer handed it back once)."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit()) or abs((now or time.time()) - int(ts)) > SKEW_S:
        return "the request's time is missing or too far from ours"
    want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
    if not hmac.compare_digest(want, sig.encode()):
        return "the signature does not match"
    return ""


def rules_of_press(body: dict) -> tuple[list[str], str]:
    """(the pressed rules' names, in the order pressed, the pressing user), or ``ValueError``."""
    if not isinstance(body, dict) or body.get("point") != "desk_action/1":
        raise ValueError("not a desk_action/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or not isinstance(ctx.get("records"), list):
        raise ValueError("no records")
    if not 1 <= len(ctx["records"]) <= MOST_RULES:
        raise ValueError("one to 100 rules a press")
    names = []
    for rec in ctx["records"]:
        if not isinstance(rec, dict) or rec.get("doctype") != RULE or not isinstance(rec.get("name"), str) \
                or not rec["name"] or rec["name"] in names:
            raise ValueError("not a rule")
        names.append(rec["name"])
    user = ctx.get("user")
    return names, user if isinstance(user, str) else ""


def _whole(v, rng: tuple[int, int, int]) -> int | None:
    least, most, blank = rng
    if v is None or v == "" or v == 0:
        return blank
    return v if isinstance(v, int) and not isinstance(v, bool) and least <= v <= most else None


def _text(v, most: int) -> str:
    return " ".join(v.split())[:most] if isinstance(v, str) else ""


class Rule:
    def __init__(self, name, shown_name, question, answers, look_back, open_days, profiles, asked_up_to):
        self.name, self.shown_name, self.question, self.answers = name, shown_name, question, answers
        self.look_back, self.open_days, self.profiles, self.asked_up_to = look_back, open_days, profiles, asked_up_to


def rule_of(r: dict) -> Rule | str:
    """A rule as the service uses it, or the sentence that says what to fix (shown to the manager)."""
    name = r.get("name") or ""
    if not r.get("enabled"):
        return f"{name} is switched off."
    shown = _text(r.get("shown_name"), 60)
    if not shown:
        return f"{name}: fill the name your customers read, then press again."
    look, days = _whole(r.get("look_back_days"), LOOK_BACK), _whole(r.get("open_days"), OPEN_DAYS)
    if look is None:
        return f"{name}: the days back must be 1 to 7."
    if days is None:
        return f"{name}: the days a link stays open must be 1 to 30."
    answers = [_text(r.get(k), 40) or d for k, d in zip(("answer_good", "answer_ok", "answer_bad"), ANSWERS)]
    profiles = sorted({p for p in r.get("profiles") or [] if isinstance(p, str) and p})
    return Rule(name, shown, _text(r.get("question"), 140) or DEFAULT_QUESTION, answers, look, days, profiles,
                r.get("asked_up_to") if isinstance(r.get("asked_up_to"), str) else "")


def rules_from_rows(rows: list) -> dict:
    """The list read names one row per rule and POS Profile (``profiles.pos_profile``): one dict per rule."""
    out = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            continue
        r = out.setdefault(row["name"], dict(row, profiles=[]))
        if row.get("pos_profile"):
            r["profiles"].append(row["pos_profile"])
    return out


def phone_of(v) -> str:
    """The first number a phone field holds, in the characters a phone number has, at most 20; fewer than six digits
    is no number."""
    m = PHONE_CHARS.search(v) if isinstance(v, str) else None
    s = m.group(0).strip()[:20].strip() if m else ""
    return s if sum(c.isdigit() for c in s) >= 6 else ""


def email_of(v) -> str:
    s = v.strip() if isinstance(v, str) else ""
    return s if len(s) <= 140 and EMAIL.fullmatch(s) else ""


def date_of(v) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def since(rule: Rule, today: datetime.date) -> datetime.date:
    """The first sale day a press reaches: *1 day back* reaches yesterday and today. There is no last day: a store
    east of UTC dates its sales ahead of UTC's date, and every sale read is asked or counted, never passed over."""
    return today - datetime.timedelta(days=rule.look_back)


def choose(sales: list, rule: Rule, walk_ins: set, asked: set, stopped: set, customers: dict, taken: set,
           today: datetime.date) -> tuple[list, dict]:
    """(the sales to ask, each with its contact, and the counts of those not asked).

    ``sales`` come oldest first by when the retailer's iVendNext received them (``creation``). ``asked`` holds the
    sales and the customers already asked in the press's days: a customer is asked once in a rule's days, and once a
    press (``taken`` is shared by every rule of the press); the latest sale of theirs in the list wins."""
    first = since(rule, today)
    counts = {"no_contact": 0, "stopped": 0, "asked": 0}
    latest = {}
    for s in sales:
        if not isinstance(s, dict) or not isinstance(s.get("name"), str):
            continue
        day, customer = date_of(s.get("posting_date")), s.get("customer")
        if s.get("docstatus") != 1 or s.get("is_return") or not day or day < first \
                or (rule.profiles and s.get("pos_profile") not in rule.profiles) or not customer \
                or customer in walk_ins:
            continue
        if customer in stopped:
            counts["stopped"] += 1
        elif s["name"] in asked or customer in asked:
            counts["asked"] += 1
        else:
            c = customers.get(customer) or {}
            mobile = phone_of(s.get("contact_mobile")) or c.get("mobile", "")
            email = email_of(s.get("contact_email")) or c.get("email", "")
            if not (mobile or email):
                counts["no_contact"] += 1
            else:
                latest[customer] = (s, mobile, email)
    chosen = [v for k, v in latest.items() if k not in taken]
    counts["asked"] += len(latest) - len(chosen)        # the customer is asked by another rule of this press
    taken.update(latest)
    return chosen, counts


def mark_after(rule: Rule, sales: list, unmade: list) -> str:
    """Where the rule's next press starts reading (sales received at or after it). Every sale read is handled: the last
    one read. A request that was not made (out of time, refused): that sale, so the next press reads it again; the
    requests already made are then found asked."""
    stamps = [s["creation"] for s in unmade if isinstance(s.get("creation"), str)]
    if stamps:
        return min(stamps)
    last = sales[-1] if sales and isinstance(sales[-1], dict) else {}
    return last["creation"] if isinstance(last.get("creation"), str) else rule.asked_up_to


def contacts_of(rows: list) -> dict:
    """The customers' own mobile number and e-mail, for a sale that carries none: the till's phone field first."""
    out = {}
    for r in rows:
        if isinstance(r, dict) and isinstance(r.get("name"), str):
            out[r["name"]] = {"mobile": phone_of(r.get("custom_phone_no")) or phone_of(r.get("mobile_no")),
                              "email": email_of(r.get("custom_email")) or email_of(r.get("email_id"))}
    return out


def sign(secret: bytes, site: str, sale: str) -> str:
    mac = hmac.new(secret, f"psf1|{site}|{sale}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode()[:SIG_LEN]


def link_of(page: str, site: str, sale: str, secret: bytes) -> str:
    """The customer's link: the page, the retailer's site and the sale with its signature, after ``#`` (never sent to
    a server in the address, never in a log)."""
    token = f"{sale}.{sign(secret, site, sale)}"
    return f"{page.rstrip('/')}/#s={urllib.parse.quote(site, safe='')}&t={urllib.parse.quote(token, safe='')}"


def sale_of_token(site: str, token, secrets: list[bytes]) -> str | None:
    """The sale a link names, when its signature is the retailer's (the current secret or the one before): else None,
    and nothing is read."""
    if not isinstance(token, str) or "." not in token or len(token) > 200:
        return None
    sale, _, sig = token.rpartition(".")
    if not sale or len(sig) != SIG_LEN:
        return None
    return sale if any(hmac.compare_digest(sign(s, site, sale), sig) for s in secrets) else None


def request_of(sale: dict, rule: Rule, mobile: str, email: str, store: str, link: str) -> dict:
    day = date_of(sale["posting_date"])
    return {"sale": sale["name"], "rule": rule.name, "customer": sale["customer"],
            "customer_name": _text(sale.get("customer_name"), 140), "mobile": mobile, "email": email,
            "pos_profile": sale.get("pos_profile") or "", "store": store, "sale_date": day.isoformat(),
            "open_until": (day + datetime.timedelta(days=rule.open_days)).isoformat(), "link": link,
            "status": "Sent"}


def message(body: str, level: str = "success", title: str = "Feedback requests") -> dict:
    """The answer in the extension point's closed vocabulary (title at most 60, body at most 280)."""
    return {"message": {"title": title[:60], "body": body if len(body) <= 280 else body[:279] + "…", "level": level},
            "refresh": True}


def press_answer(made: int, counts: dict, failed: int, left: bool, problems: list[str]) -> dict:
    parts = [f"Made {made} feedback request{'' if made == 1 else 's'}." if made else "No new feedback requests."]
    why = [f"{counts[k]} {w}" for k, w in (("asked", "already asked"), ("stopped", "asked us to stop"),
                                          ("no_contact", "with no mobile number or e-mail")) if counts.get(k)]
    if why:
        parts.append("Not asked: " + ", ".join(why) + ".")
    if failed:
        parts.append(f"{failed} could not be made.")
    if left:
        parts.append("More sales wait: press again.")
    parts += problems
    return message(" ".join(parts), "warning" if left or failed or problems else "success")


def today_utc(now: float | None = None) -> datetime.date:
    return datetime.datetime.fromtimestamp(now if now is not None else time.time(), datetime.timezone.utc).date()


def page_of(req: dict, rule: dict, today: datetime.date) -> dict:
    """What the customer's page shows: never a name, a number or an amount."""
    words = rule_of(dict(rule, enabled=1)) if isinstance(rule, dict) else None
    words = words if isinstance(words, Rule) else None
    out = {"name": words.shown_name if words else "", "date": str(req.get("sale_date") or "")[:10],
           "question": words.question if words else DEFAULT_QUESTION,
           "answers": words.answers if words else list(ANSWERS), "stopped": bool(req.get("asked_to_stop"))}
    until = date_of(req.get("open_until"))
    out["state"] = "answered" if req.get("answer") else ("closed" if not until or today > until else "open")
    return out


def answer_of(body) -> tuple[int | None, str, bool]:
    """(the answer's place 0 to 2, or None for *stop* alone, the comment, *stop these messages*), or ``ValueError``."""
    if not isinstance(body, dict):
        raise ValueError("not an answer")
    a, comment, stop = body.get("answer"), body.get("comment"), body.get("stop")
    if a is not None and (isinstance(a, bool) or a not in (0, 1, 2)):
        raise ValueError("not an answer")
    if comment is not None and not isinstance(comment, str) or stop is not None and not isinstance(stop, bool):
        raise ValueError("not an answer")
    if a is None and not stop:
        raise ValueError("no answer")
    return a, " ".join((comment or "").split())[:COMMENT_MAX], bool(stop)


def now_text(now: float) -> str:
    """The time as text, said in UTC: a date-time field would show it labelled with the site's own zone."""
    return datetime.datetime.fromtimestamp(now, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
