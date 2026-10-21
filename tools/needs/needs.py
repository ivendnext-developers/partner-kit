#!/usr/bin/env python3
"""needs.py — the needs catalogue: one short card per customer need, in needs/<area>/<id>.md. It checks the cards and finds them.

    python3 tools/needs/needs.py check                    # every card against the rules below; exit 0 = CARDS GREEN (warnings never fail)
    python3 tools/needs/needs.py search <words>           # the cards whose words match, best first
    python3 tools/needs/needs.py show <id>                # one card, as written
    python3 tools/needs/needs.py blueprint <id> [<id> …]  # the rows for section (b) of kit/blueprint_template.md
    python3 tools/needs/needs.py stale [--days N]         # cards checked more than N days ago (default 90): a to-do, never a failure
    python3 tools/needs/needs.py backlinks                # for each recipe and sample, the needs it serves

A card is front matter (`key: value` lines between two `---` lines) and three sections: *What you build*, *Limits* and *Tell the
customer*. The site build (site/build.py) imports load() and check() from this file, so the tool and the site cannot disagree.
Python 3 standard library only; no network, no secret. The format and the closed lists: needs/README.md.
"""
from __future__ import annotations

import datetime
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

STATUSES = {"ready": "Ready", "ready-with-limits": "Ready, with limits", "not-yet": "Not yet", "not-possible": "Not possible"}
AREAS = {"prices": "Prices and promotions", "stock": "Stock and buying", "customers": "Customers and loyalty",
         "till": "Till controls and approvals", "documents": "Documents and print", "reports": "Reports and data",
         "integrations": "Integrations, payments and hardware", "setup": "Setup and administration"}
DOORS = {"configure": "Configure", "outside-app": "Outside app", "event-feed": "Event feed", "till-key": "Till key",
         "manifest": "Manifest", "sandboxed-function": "Sandboxed function", "check-before-payment": "Check before payment",
         "document-check": "Document check", "capture-on-event": "Capture on an event", "field-rules": "Field rules",
         "save-rules": "Save rules", "desk-action": "Desk action", "partner-page": "Partner page", "scan-source": "Scan source",
         "label-layout": "Label layout", "wallet": "Wallet", "fiscal-reader": "Fiscal reader", "fulfil-at-sale": "Fulfil at sale",
         "payment-connector": "Payment connector", "our-connector": "Our connector", "receipt": "Receipt settings",
         "request": "Request", "none": "None"}
# The topics of each area (a card's `topic:` line): the headings an area's page is grouped under. At most six per area; a
# topic with fewer than two cards is a warning from `check`, never a failure, so a lane adding one card to a new topic is not held.
TOPICS = {
    "prices": {"price-lists": "Price lists", "promotions": "Promotions and coupons", "member-prices": "Member prices",
               "fees-and-add-ons": "Fees and add-ons"},
    "stock": {"counts": "Counts", "alerts-and-reorder": "Alerts and reorder", "who-sees-stock": "Who sees which stock",
              "batches-and-expiry": "Batches and expiry", "handheld-and-scanning": "Handheld and scanning"},
    "customers": {"loyalty-and-wallets": "Loyalty, gift cards and wallets", "customer-records": "New and existing customers",
                  "history-and-crm": "History and CRM"},
    "till": {"manager-approvals": "Manager approvals", "limits-on-a-sale": "Limits on a sale", "payment": "Payment",
             "questions-during-the-sale": "Questions and details during the sale", "till-screen": "The till screen and terminals",
             "cash-voids-returns": "Cash, voids and returns"},
    "documents": {"receipts": "Receipts", "layouts-and-labels": "Print layouts and labels", "approvals": "Approvals",
                  "checks-on-save": "Numbering and checks on save", "own-records-and-fields": "Your own records, fields and buttons"},
    "reports": {"reports-and-bi": "Reports and BI", "scheduled-jobs": "Scheduled jobs"},
    "integrations": {"erp": "ERP", "online-shops-and-orders": "Online shops and order systems",
                     "payments-and-fiscal": "Payments and fiscal", "events": "Events from the shop"},
    "setup": {"companies-and-servers": "Companies, countries and servers", "roles-and-data-rules": "Roles, lists and data rules"},
}
BLOCKED = {"extension-point", "product-work"}
KEYS = ("id", "title", "area", "topic", "asks", "status", "door", "blocked-by", "recipe", "sample", "request", "verified")
SECTIONS = ("What you build", "Limits", "Tell the customer")
MAX_LINES = 40
# The two upstream names are never written in a card. The pattern is written so that this file does not contain either word.
UPSTREAM = re.compile(r"fr[a]ppe|erp[n]ext", re.I)
# "extension point" is never shortened: a bare point or points is refused, except in these phrases.
POINT_OK = re.compile(r"extension[ -]points?|loyalty points?|points? of sale", re.I)
HANDLE = re.compile(r"^P-[A-Z0-9]+$")
MAX_RELATED = 4                                   # an optional `related:` line names at most four other cards, by id
BLUEPRINT_HEAD = "| # | Need (customer's words) | Card | Status | Door | Limits and note |\n|---|---|---|---|---|---|"


class Card:
    def __init__(self, path: pathlib.Path, root: pathlib.Path):
        self.path, self.root = path, root
        self.rel = path.relative_to(root).as_posix()
        self.text = path.read_text("utf-8")
        self.meta: dict[str, str] = {}
        self.body = ""
        self.sections: dict[str, str] = {}
        m = re.match(r"---\n(.*?)\n---\n?(.*)\Z", self.text, re.S)
        if m:
            for line in m.group(1).splitlines():
                key, sep, value = line.partition(":")
                if sep and key.strip():
                    self.meta[key.strip()] = value.strip()
            self.body = m.group(2)
            for head, text in re.findall(r"^## (.+?)\s*\n(.*?)(?=^## |\Z)", self.body, re.S | re.M):
                self.sections[head.strip()] = text.strip()

    def __getattr__(self, name: str) -> str:            # card.id, card.asks, card.blocked_by …
        return self.__dict__["meta"].get(name.replace("_", "-"), "")

    @property
    def verdict(self) -> str:
        word = STATUSES.get(self.status, self.status)
        return f"{word} ({len(self.limits)})" if self.status == "ready-with-limits" else word

    @property
    def limits(self) -> list[str]:
        return [ln[2:].strip() for ln in self.sections.get("Limits", "").splitlines() if ln.startswith("- ")]

    @property
    def requests(self) -> list[str]:
        return [h.strip() for h in self.request.split(",") if h.strip() and h.strip() != "-"]

    @property
    def related(self) -> list[str]:                     # the optional hand-written `related:` ids, in the order written
        return [i.strip() for i in self.meta.get("related", "").split(",") if i.strip() and i.strip() != "-"]

    def paths(self, key: str) -> list[str]:
        return [p.strip() for p in self.meta.get(key, "").split(",") if p.strip() and p.strip() != "none"]

    def checked_on(self) -> datetime.date | None:
        m = re.search(r"\d{4}-\d{2}-\d{2}", self.verified)
        return datetime.date.fromisoformat(m.group()) if m else None


def load(root: pathlib.Path = ROOT) -> list[Card]:
    return [Card(p, root) for p in sorted((root / "needs").glob("*/*.md"))]


def cited(cards: list[Card]) -> set[str]:
    return {p.rstrip("/") for c in cards for key in ("recipe", "sample") for p in c.paths(key)}


def reference(root: pathlib.Path) -> dict[str, str]:
    """needs/reference.txt: recipes and samples that are reference, not the answer to a need. One `path — reason` per line."""
    f = root / "needs" / "reference.txt"
    out = {}
    for line in (f.read_text("utf-8").splitlines() if f.exists() else []):
        if line.strip() and not line.startswith("#"):
            path, _, reason = line.partition(" — ")
            out[path.strip().rstrip("/")] = reason.strip()
    return out


def check(root: pathlib.Path = ROOT) -> list[str]:
    """Every rule a card must keep. Returns one line per fault; an empty list is green."""
    cards, bad = load(root), []
    seen: dict[str, str] = {}
    for c in cards:
        err = lambda msg, c=c: bad.append(f"{c.rel}: {msg}")
        if not c.meta:
            err("no front matter (a card starts with a line of three dashes)")
            continue
        for k in KEYS:
            if not c.meta.get(k):
                err(f"no {k}: line")
        for s in SECTIONS:
            if s not in c.sections:
                err(f"no '## {s}' section")
        if c.id in seen:
            err(f"id {c.id} is also used by {seen[c.id]}")
        seen.setdefault(c.id, c.rel)
        if c.path.stem != c.id:
            err(f"the file name {c.path.name} is not the id {c.id}")
        if c.area not in AREAS:
            err(f"unknown area {c.area!r} (one of: {', '.join(AREAS)})")
        elif c.path.parent.name != c.area:
            err(f"area {c.area} but the card is in needs/{c.path.parent.name}/")
        elif c.topic and c.topic not in TOPICS.get(c.area, {}):
            err(f"unknown topic {c.topic!r} for area {c.area} (one of: {', '.join(TOPICS.get(c.area, {}))})")
        if c.door not in DOORS:
            err(f"unknown door {c.door!r} (one of: {', '.join(DOORS)})")
        if c.status not in STATUSES:
            err(f"unknown status {c.status!r} (one of: {', '.join(STATUSES)})")
        for key in ("recipe", "sample"):
            for p in c.paths(key):
                if not (root / p).exists():
                    err(f"{key} {p} does not exist")
        for h in c.requests:
            if not HANDLE.match(h):
                err(f"request {h!r} is not a handle such as P-CHECK")
        lines = c.text.count("\n") + (not c.text.endswith("\n"))
        if lines > MAX_LINES:
            err(f"{lines} lines: a card is at most {MAX_LINES} (aim for 25)")
        if UPSTREAM.search(c.text):
            err("names an upstream product or framework: call it iVendNext")
        if re.search(r"\bpoints?\b", POINT_OK.sub("", c.text), re.I):
            err("'point' on its own: write 'extension point' in full")
        limits = c.limits
        if c.status == "ready" and c.sections.get("Limits", "") not in ("", "None known."):
            err("ready, but its Limits section says more than 'None known.': make it ready-with-limits")
        if c.status == "ready-with-limits" and not limits:
            err("ready-with-limits, but no '- ' line under Limits")
        if c.status == "not-yet":
            if c.blocked_by not in BLOCKED:
                err("not-yet needs blocked-by: extension-point or product-work")
            if c.door != "request":
                err("a not-yet card's door is request")
            if c.blocked_by == "extension-point" and not c.requests:
                err("blocked by an extension point, but names no request handle")
            if c.blocked_by == "product-work" and "**Ask us:**" not in c.sections.get("Limits", ""):
                err("blocked by product work, but no '**Ask us:**' line under Limits")
        elif c.blocked_by not in ("", "-"):
            err(f"blocked-by is for not-yet cards only (write -), not {c.status}")
        if c.status == "not-possible":
            if "**Instead:**" not in c.sections.get("Limits", ""):
                err("not-possible, but no '**Instead:**' line under Limits")
            if c.door != "none":
                err("a not-possible card's door is none")
        elif c.door == "none":
            err("door none is for not-possible cards only")
        if c.door == "request" and c.status != "not-yet":
            err("door request is for not-yet cards only")
    ids = {c.id for c in cards}
    for c in cards:
        rel = c.related
        if len(rel) > MAX_RELATED:
            bad.append(f"{c.rel}: related names {len(rel)} cards; at most {MAX_RELATED}")
        for i in rel:
            if i == c.id:
                bad.append(f"{c.rel}: related names the card itself")
            elif i not in ids:
                bad.append(f"{c.rel}: related names {i}, which is not a card's id")
    refs = reference(root)
    for p in refs:
        if not (root / p).exists():
            bad.append(f"needs/reference.txt: {p} does not exist")
        elif not refs[p]:
            bad.append(f"needs/reference.txt: {p} gives no reason (write: <path> — <reason>)")
    used = cited(cards)
    proofs = [f"recipes/{p.name}" for p in sorted((root / "recipes").glob("*.md"))]
    proofs += [f"samples/{p.name}" for p in sorted((root / "samples").iterdir()) if p.is_dir() and (p / "README.md").exists()]
    for p in proofs:
        if p not in used and p not in refs:
            bad.append(f"{p}: no card cites it and needs/reference.txt does not list it")
    return bad


def warnings(root: pathlib.Path = ROOT) -> list[str]:
    """What check() lets through but a person should look at: a topic with fewer than two cards. Never a failure."""
    cards = load(root)
    out = []
    for area, topics in TOPICS.items():
        for t in topics:
            n = sum(1 for c in cards if c.area == area and c.topic == t)
            if n < 2:
                out.append(f"topic {area}/{t} has {n} card(s): a topic is meant to group two or more")
    return out


STOP = {"of", "on", "in", "to", "an", "at", "by", "or", "is", "it", "as", "be", "the", "and", "for", "our", "we", "us", "a"}


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1 and w not in STOP}


def search(cards: list[Card], query: str) -> list[tuple[int, Card]]:
    want = words(query)
    hits = []
    for c in cards:
        score = 3 * len(want & words(c.asks + " " + c.title)) + len(want & words(c.body + " " + c.door))
        if score:
            hits.append((score, c))
    return sorted(hits, key=lambda h: (-h[0], h[1].asks.lower()))


def blueprint_rows(cards: list[Card], ids: list[str]) -> tuple[list[str], list[str]]:
    by_id = {c.id: c for c in cards}
    rows, missing = [], []
    for n, i in enumerate(ids, 1):
        c = by_id.get(i)
        if not c:
            missing.append(i)
            continue
        note = "; ".join(c.limits + ([f"ask for {', '.join(c.requests)}"] if c.requests else []))
        rows.append(f"| {n} | {c.asks} | {c.id} | {c.verdict} | {DOORS.get(c.door, c.door)} | {note} |")
    return rows, missing


def backlinks(cards: list[Card]) -> dict[str, list[Card]]:
    out: dict[str, list[Card]] = {}
    for c in cards:
        for key in ("recipe", "sample"):
            for p in c.paths(key):
                out.setdefault(p.rstrip("/"), []).append(c)
    return out


def stale(cards: list[Card], days: int, today: datetime.date | None = None) -> list[Card]:
    today = today or datetime.date.today()
    return [c for c in cards if not c.checked_on() or (today - c.checked_on()).days > days]


def main(argv: list[str]) -> int:
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    cards = load()
    if cmd == "check":
        bad = check()
        for b in bad:
            print("REFUSED " + b)
        for w in warnings():
            print("WARNING " + w)
        print(f"{len(cards)} cards: " + ("CARDS GREEN" if not bad else f"{len(bad)} fault(s)"))
        return 1 if bad else 0
    if cmd == "search" and args:
        hits = search(cards, " ".join(args))
        for _, c in hits[:15]:
            print(f"{c.id:40} {c.verdict:22} {c.asks}")
        print(f"{len(hits)} card(s) share words with the need, closest first: check the top card answers it as asked."
              if hits else "0 cards match.")
        print("If no card answers the need, place it on the ladder (guide chapter 3) or ask for an extension point "
              "(feedback/point_request.md).")
        return 0 if hits else 1
    if cmd == "show" and len(args) == 1:
        c = next((c for c in cards if c.id == args[0]), None)
        print(c.text if c else f"no card {args[0]}: try `needs.py search <words>`")
        return 0 if c else 1
    if cmd == "blueprint" and args:
        rows, missing = blueprint_rows(cards, args)
        print(BLUEPRINT_HEAD)
        print("\n".join(rows))
        for m in missing:
            print(f"no card {m}", file=sys.stderr)
        return 1 if missing else 0
    if cmd == "stale":
        i = args.index("--days") + 1 if "--days" in args else -1
        n = "90" if i < 0 else (args[i] if i < len(args) else "")
        if not n.isdigit():
            print("usage: needs.py stale [--days N]")
            return 2
        days = int(n)
        old = stale(cards, days)
        for c in old:
            print(f"{c.id:40} {c.verified}")
        print(f"{len(old)} of {len(cards)} cards checked more than {days} days ago (a to-do, not a failure)")
        return 0
    if cmd == "backlinks":
        for path, cs in sorted(backlinks(cards).items()):
            print(f"{path}: " + ", ".join(c.id for c in cs))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
