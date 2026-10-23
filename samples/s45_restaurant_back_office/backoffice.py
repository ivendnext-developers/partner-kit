"""S45 — *Restaurant back office*: the pure core (no framework, no network), shared by the service and its tests.

Three Desk buttons send one signed POST per press each (the Desk action extension point, ``desk_action/1``):

    Issue ingredients   on the shop's settings record (one per company)  → /press/issue
    Work out food cost  on a food cost record (a store and a period)     → /press/foodcost
    Check allergens     on the Item list or an item's form               → /press/allergens

``verify`` checks the signature the shop puts on every call; ``records_of`` takes a press's records; ``parts_of``
explodes a dish's engine recipe (its BOM) into the stock items it uses; ``group_lines`` puts the day's sold lines into
one issue per store and day; ``issue_doc`` and ``stock_entry`` are the two records the service writes for a group;
``short_of`` names every part a store is short of; ``food_cost`` works out a period's theoretical and actual food cost
from the shop's own ledger; ``allergens_missing`` compares a dish's allergens with its recipe's. ⛔ No answer writes
anything: the service writes through its own API key and its own rights, BEFORE it answers.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import time

PREFIX = "PP RBO"
FIELD = "pp_rbo"            # the fields the app adds to the shop's records: <FIELD>_allergens on Item, <FIELD>_issue on
                            # Stock Entry
SKEW_S = 300                # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
MOST_RECORDS = 100          # the Desk action's own limit for a list press
DEPTH = 5                   # recipes inside recipes: deeper than this is refused as a loop
PLACES = 6                  # quantities are kept to six decimals; the shop rounds to its own precision when it books
EU_14 = ["Celery", "Cereals containing gluten", "Crustaceans", "Eggs", "Fish", "Lupin", "Milk", "Molluscs", "Mustard",
         "Tree nuts", "Peanuts", "Sesame", "Soya", "Sulphites"]


def use_prefix(prefix: str):
    """The record types and fields under another prefix: *IVENDNEXT RBO Issue*, ``ivendnext_rbo_allergens`` for the
    library's app."""
    global PREFIX, FIELD
    PREFIX, FIELD = prefix, prefix.lower().replace(" ", "_")


def dt(name: str) -> str:
    """The app's own record type: ``dt("Issue")`` is *PP RBO Issue*."""
    return f"{PREFIX} {name}"


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


def records_of(body: dict, doctype: str, most: int = MOST_RECORDS) -> list[str]:
    """The records a press names, in its order, or ``ValueError``: checked before anything is read or written."""
    if not isinstance(body, dict) or body.get("point") != "desk_action/1":
        raise ValueError("not a desk_action/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or not isinstance(ctx.get("records"), list):
        raise ValueError("no records")
    recs = ctx["records"]
    if not 1 <= len(recs) <= most:
        raise ValueError(f"one to {most} records a press")
    out = []
    for rec in recs:
        if not isinstance(rec, dict) or rec.get("doctype") != doctype or not isinstance(rec.get("name"), str) \
                or not rec["name"]:
            raise ValueError(f"not a {doctype}")
        if rec["name"] not in out:
            out.append(rec["name"])
    return out


def num(v) -> float:
    """A number the shop sent, or 0 (never a bool, never text)."""
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def date_of(v) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def clock_of(v) -> str:
    """A time of day the shop sent, as ``HH:MM:SS``: the shop's API prints a time's seconds without a leading zero
    (``11:35:9.97``, measured on the bench), so a time is never compared or sent back as the text it came in."""
    t = seconds_of(v)
    return "" if t is None else f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def moment_of(v) -> str:
    """A date and time the shop sent, as text that sorts (``2026-10-23 11:04:18``), or ``""``."""
    d, _, t = str(v or "").replace("T", " ").partition(" ")
    day = date_of(d)
    return f"{day.isoformat()} {clock_of(t.split('+')[0]) or '00:00:00'}" if day else ""


def booked_from(sale: dict, start: str) -> bool:
    """A sale counts only when it was booked at or after the settings' start (its own date and time, the shop's clock)."""
    return f"{str(sale.get('posting_date'))[:10]} {clock_of(sale.get('posting_time')) or '00:00:00'}" >= start


def seconds_of(v) -> int | None:
    """A time of day the shop sent (``13:05:09.123``, ``9:00:00``) as seconds after midnight, or None."""
    try:
        h, m, *s = str(v).split(":")
        return int(h) * 3600 + int(m) * 60 + int(float(s[0]) if s else 0)
    except (ValueError, IndexError):
        return None


# ── recipes ──────────────────────────────────────────────────────────────────────────────────────────────────────────
class RecipeError(Exception):
    """A recipe the app cannot read: a loop, or recipes nested deeper than ``DEPTH``."""


def parts_of(item: str, qty: float, items: dict, boms: dict, depth: int = 0, seen: tuple = ()) -> tuple[dict, list]:
    """``({stock item: quantity in its stock unit}, [notes])`` for ``qty`` of ``item`` in its stock unit.

    ``items[code]``: ``{"is_stock_item", "default_bom"}``; ``boms[name]``: ``{"quantity", "items": [{"item_code",
    "stock_qty", "bom_no"}]}`` — the engine's own recipe (BOM): ``stock_qty`` of a part makes ``quantity`` of the dish.
    A part that is a stock item is issued as it is (a sauce the kitchen makes and stocks is issued as the sauce). A part
    that is not stocked is opened through its own recipe (the row's ``bom_no``, else the part's default recipe); one with
    no recipe is skipped and named in the notes (water, say). A dish that is itself a stock item is never opened: the
    shop already moves its stock when it books the sale."""
    meta = items.get(item) or {}
    if meta.get("is_stock_item"):
        return {item: qty}, []
    return _open(item, meta.get("default_bom"), qty, items, boms, depth, seen)


def _open(item, bom_name, qty, items, boms, depth, seen):
    if not bom_name:
        return {}, [f"{item}: no recipe"]
    if bom_name in seen or depth >= DEPTH:
        raise RecipeError(f"{item}'s recipe {bom_name} goes round in a loop or deeper than {DEPTH} recipes")
    bom = boms.get(bom_name)
    if not bom or num(bom.get("quantity")) <= 0:
        return {}, [f"{item}: recipe {bom_name} is not active"]
    out, notes = {}, []
    for row in bom.get("items") or []:
        part, per = row.get("item_code"), num(row.get("stock_qty")) / num(bom["quantity"])
        if not part or per <= 0:
            continue
        need = qty * per
        if (items.get(part) or {}).get("is_stock_item"):
            got, why = {part: need}, []
        else:
            got, why = _open(part, row.get("bom_no") or (items.get(part) or {}).get("default_bom"), need, items, boms,
                             depth + 1, seen + (bom_name,))
        for k, v in got.items():
            out[k] = out.get(k, 0.0) + v
        notes += why
    return out, notes


def boms_to_read(codes, items: dict, deep: bool = False) -> list[str]:
    """The recipes the items name directly. For the stock issue only an item that is not stocked is opened (a stocked
    sauce is issued as the sauce); ``deep`` (the allergen check) opens a stocked one's recipe too, because its
    ingredients' allergens are in the dish."""
    return sorted({(items.get(c) or {}).get("default_bom") for c in codes
                   if (deep or not (items.get(c) or {}).get("is_stock_item")) and (items.get(c) or {}).get("default_bom")})


def bom_rows_to_read(boms: dict, items: dict, deep: bool = False) -> list[str]:
    """Recipes named inside the recipes read so far and not read yet (a row's own recipe first, else the part's)."""
    want = set()
    for b in boms.values():
        for row in b.get("items") or []:
            meta = items.get(row.get("item_code")) or {}
            if meta and (deep or not meta.get("is_stock_item")):
                want.add(row.get("bom_no") or meta.get("default_bom"))
    return sorted(x for x in want if x and x not in boms)


# ── the day's sales, one issue per store and day ─────────────────────────────────────────────────────────────────────
def day_part_of(sold_at, parts: list[dict]) -> str:
    """The shop's name for the part of the day a sale was rung in (*Breakfast*, *Lunch*), from its day parts; a part
    whose end is before its start runs past midnight (*Late*, 22:00 to 02:00). Blank when none covers the time."""
    t = seconds_of(sold_at)
    if t is None:
        return ""
    for p in parts or []:
        a, b = seconds_of(p.get("from_time")), seconds_of(p.get("to_time"))
        if a is None or b is None or not p.get("day_part"):
            continue
        if (a <= t < b) if a < b else (t >= a or t < b):
            return p["day_part"]
    return ""


def store_of(sale: dict, line: dict, profile_stores: dict) -> str:
    """The store a line was sold from: the line's own, else the sale's, else its till's profile's."""
    return line.get("warehouse") or sale.get("set_warehouse") or profile_stores.get(sale.get("pos_profile")) or ""


def group_lines(sales: list[dict], lines: list[dict], items: dict, profile_stores: dict, day_parts: list[dict],
                kitchen: str = "") -> dict:
    """``{(store, posting date): {"store", "issue_from", "posting_date", "posting_time", "sales", "lines"}}`` — every
    line of every sale, so a sale is claimed once whatever it sold. ``lines`` rows carry what the sales report reads:
    the sale, the item, its quantity in the stock unit, the amount net of tax, who rang it, when, its day part, and
    whether the dish has a recipe."""
    by_sale = {s["name"]: s for s in sales}
    out: dict = {}
    for ln in lines:
        sale = by_sale.get(ln.get("parent"))
        if not sale:
            continue
        store = store_of(sale, ln, profile_stores)
        key = (store, str(sale.get("posting_date"))[:10])
        g = out.setdefault(key, {"store": store, "issue_from": kitchen or store, "posting_date": key[1],
                                 "posting_time": "00:00:00", "sales": [], "lines": []})
        if sale["name"] not in g["sales"]:
            g["sales"].append(sale["name"])
        t = clock_of(sale.get("posting_time")) or "00:00:00"
        if (seconds_of(t) or 0) > (seconds_of(g["posting_time"]) or 0):
            g["posting_time"] = t
        meta = items.get(ln.get("item_code")) or {}
        qty = num(ln.get("stock_qty")) or num(ln.get("qty"))
        g["lines"].append({"sale": sale["name"], "item_code": ln.get("item_code"), "qty": qty,
                           "amount": round(num(ln.get("net_amount")), 2), "server": sale.get("owner") or "",
                           "sold_at": t, "day_part": day_part_of(t, day_parts),
                           "has_recipe": int(not meta.get("is_stock_item") and bool(meta.get("default_bom")))})
    return out


def sharing_sales(groups: dict) -> list[list]:
    """The groups' keys in sets a press writes together, oldest day first: the store-days that share a sale (one whose
    lines left two stores) are one set, so a press never claims a sale at one store and stops before the other."""
    order = sorted(groups, key=lambda k: (k[1], k[0]))
    owner, sets = {}, []
    for key in order:
        joined = [x for x in sets if any(owner.get(s) is x for s in groups[key]["sales"])]
        mine = [key] + [k for x in joined for k in x]
        sets = [x for x in sets if all(x is not y for y in joined)] + [mine]
        for k in mine:
            for s in groups[k]["sales"]:
                owner[s] = mine
    return sorted((sorted(x, key=order.index) for x in sets), key=lambda x: order.index(x[0]))


def need_of(group: dict, items: dict, boms: dict) -> tuple[dict, list]:
    """What a group's dishes took from stock: ``({part: quantity}, notes)``. Returned lines (a negative quantity) take
    nothing back: the food was made."""
    need, notes, dishes = {}, [], []
    for ln in group["lines"]:
        if ln["qty"] <= 0:
            continue
        if not ln["has_recipe"]:        # a dish rung before its recipe was made: its sale is taken, so say so
            note = f"{ln['item_code']}: sold with no recipe"
            if not (items.get(ln["item_code"]) or {}).get("is_stock_item") and note not in dishes:
                dishes.append(note)
            continue
        got, why = parts_of(ln["item_code"], ln["qty"], items, boms)
        for k, v in got.items():
            need[k] = need.get(k, 0.0) + v
        notes += [w for w in why if w not in notes]
    return {k: round(v, PLACES) for k, v in sorted(need.items()) if round(v, PLACES) > 0}, notes + dishes


def taken_before(name: str, amends: dict, claimed: set) -> bool:
    """Whether a sale amended in Desk amends, at any remove, a sale an issue already names (``amends``: sale → the
    sale it amends, cancelled ones included). Its ingredients went with that issue; a change in quantity is the shop's
    own stock entry."""
    seen = set()
    while name and name not in seen:
        seen.add(name)
        name = amends.get(name)
        if name in claimed:
            return True
    return False


def issue_doc(company: str, group: dict, need: dict, items: dict, notes: list) -> dict:
    """The app's own record of one group, written BEFORE the stock entry: it claims the group's sales, so a sale is
    never issued twice, and it holds the parts, so a press after a crash finishes the same issue."""
    return {"company": company, "store": group["store"], "issue_from": group["issue_from"],
            "posting_date": group["posting_date"], "posting_time": group["posting_time"],
            "status": "Pending" if need else "Nothing to issue", "sales": "\n".join(group["sales"]),
            "sale_count": len(group["sales"]), "food_sales": round(sum(ln["amount"] for ln in group["lines"]), 2),
            "note": "; ".join(notes)[:500],
            "lines": group["lines"],
            "parts": [{"item_code": k, "qty": v, "uom": (items.get(k) or {}).get("stock_uom")} for k, v in need.items()]}


def stock_entry(company: str, issue: dict, now: bool = False) -> dict:
    """The shop's own Material Issue for an issue's parts, from its store, submitted in the same call (``docstatus`` 1:
    one write, all or nothing): dated at the time of the day's last sale, or, ``now``, left to the shop to date at the
    moment it books it (the stock came in after the sales, so the sales' own time is short of it). No account is sent:
    the shop books each row as it books any issue, to the ingredient's own expense account (its Item Defaults, else its
    Item Group's, else the company's stock adjustment account), so a shop that wants its cost of goods sold sets that
    account on its ingredients."""
    rows = []
    for p in issue["parts"]:
        row = {"item_code": p["item_code"], "qty": p["qty"], "s_warehouse": issue["issue_from"]}
        if p.get("uom"):
            row.update(uom=p["uom"], stock_uom=p["uom"], conversion_factor=1)
        rows.append(row)
    when = {} if now else {"posting_date": issue["posting_date"], "posting_time": issue["posting_time"],
                           "set_posting_time": 1}
    return {"stock_entry_type": "Material Issue", "purpose": "Material Issue", "company": company, **when,
            "from_warehouse": issue["issue_from"], f"{FIELD}_issue": issue["name"],
            "remarks": f"{PREFIX}: the ingredients of {issue['sale_count']} sales at {issue['store']} on "
                       f"{issue['posting_date']} ({issue['name']})" + (", booked when the stock came in" if now else ""),
            "items": rows, "docstatus": 1}


def ours_by_remarks(remarks) -> bool:
    """A Material Issue the app made, known by the remarks it wrote (``stock_entry``), when its link field is gone."""
    return isinstance(remarks, str) and remarks.startswith(f"{PREFIX}: the ingredients of ")


def short_of(parts: list[dict], on_hand: dict) -> list[tuple[str, float, float]]:
    """``[(part, needed, on hand)]`` for every part the store has less of than the issue needs."""
    out = []
    for p in parts:
        have = num(on_hand.get(p["item_code"]))
        if have + 1e-9 < num(p["qty"]):
            out.append((p["item_code"], num(p["qty"]), have))
    return out


def short_note(short: list, store: str) -> str:
    def q(x):
        return f"{x:g}"
    named = ", ".join(f"{p} (needs {q(n)}, has {q(h)})" for p, n, h in short[:6])
    more = f" and {len(short) - 6} more" if len(short) > 6 else ""
    return (f"Not issued: {store} is short of {named}{more}. Receive or count them, then press Issue ingredients "
            "again.")


# ── food cost ────────────────────────────────────────────────────────────────────────────────────────────────────────
SOLD = ("Sales Invoice", "POS Invoice", "Delivery Note")


def food_cost(ledger: list[dict], ours: set, other_issues: set, counts: list[dict], sales_amount: float,
              uoms: dict) -> dict:
    """A period's food cost at one store, from the shop's own stock ledger rows (``item_code``, ``actual_qty``,
    ``stock_value_difference``, ``voucher_type``, ``voucher_no``) and its stock counts' rows at that store
    (``item_code``, ``qty`` counted, ``current_qty`` the books held, ``amount_difference``).

    Per item, what left the store: **by recipe** (the app's issues, ``ours``), **sold as it is** (a drink sold from
    stock), **other issues** (waste, staff meals: the shop's own Material Issues), and the **count difference** (what
    the shop's counts found missing; found extra counts back). Theoretical = by recipe + sold as it is; actual = all
    four. Receipts and transfers are not use and are left out."""
    rows: dict = {}

    def add(item, col, qty, value):
        r = rows.setdefault(item, {"item_code": item, "uom": uoms.get(item) or "", "recipe_qty": 0.0, "sold_qty": 0.0,
                                   "other_qty": 0.0, "count_qty": 0.0, "recipe_value": 0.0, "sold_value": 0.0,
                                   "other_value": 0.0, "count_value": 0.0})
        r[f"{col}_qty"] += qty
        r[f"{col}_value"] += value

    for e in ledger:
        vt, vn = e.get("voucher_type"), e.get("voucher_no")
        q, v = -num(e.get("actual_qty")), -num(e.get("stock_value_difference"))
        if vt == "Stock Entry" and vn in ours:
            add(e["item_code"], "recipe", q, v)
        elif vt == "Stock Entry" and vn in other_issues:
            add(e["item_code"], "other", q, v)
        elif vt in SOLD:
            add(e["item_code"], "sold", q, v)
    for c in counts:        # the count's own difference is stored as text: counted less what the books held, both numbers
        add(c["item_code"], "count", num(c.get("current_qty")) - num(c.get("qty")), -num(c.get("amount_difference")))
    lines, theo, act = [], 0.0, 0.0
    for item in sorted(rows):
        r = rows[item]
        r["actual_qty"] = r["recipe_qty"] + r["sold_qty"] + r["other_qty"] + r["count_qty"]
        t = r["recipe_value"] + r["sold_value"]
        a = t + r["other_value"] + r["count_value"]
        r.update(theoretical_value=t, actual_value=a, variance_value=a - t)
        theo, act = theo + t, act + a
        lines.append({k: (round(x, PLACES) if k.endswith("_qty") else round(x, 2)) if isinstance(x, float) else x
                      for k, x in r.items() if k not in ("recipe_value", "sold_value", "other_value", "count_value")})
    pct = (lambda x: round(100 * x / sales_amount, 2) if sales_amount > 0 else 0.0)
    return {"lines": lines, "food_sales": round(sales_amount, 2), "theoretical_cost": round(theo, 2),
            "actual_cost": round(act, 2), "theoretical_pct": pct(theo), "actual_pct": pct(act)}


# ── allergens ────────────────────────────────────────────────────────────────────────────────────────────────────────
def words_of(text) -> list[str]:
    """A field's allergens as the shop wrote them: comma, semicolon or one per line; *Contains:* dropped."""
    if not isinstance(text, str):
        return []
    t = text.replace(";", ",").replace("\n", ",")
    if t.lower().startswith("contains:"):
        t = t[len("contains:"):]
    out = []
    for w in t.split(","):
        w = " ".join(w.split())
        if w and w.lower() not in [x.lower() for x in out]:
            out.append(w)
    return out


def allergens_missing(dish: str, items: dict, boms: dict, allergens: dict) -> tuple[list[str], list[str]]:
    """``(allergens of the recipe's parts the dish does not name, the parts they come from)`` — over every part the
    recipe reaches at every depth, a stocked sauce's own recipe included. ``allergens[code]`` is the item's own field."""
    have = {w.lower() for w in words_of(allergens.get(dish))}
    missing, sources = [], []
    for part in sorted(recipe_items(dish, items, boms)):
        for w in words_of(allergens.get(part)):
            if w.lower() not in have:
                if w.lower() not in [m.lower() for m in missing]:
                    missing.append(w)
                if part not in sources:
                    sources.append(part)
    return missing, sources


def recipe_items(item: str, items: dict, boms: dict, depth: int = 0, seen: tuple = (), bom_name: str | None = None) -> set:
    """Every item a recipe names, at every depth: a part's own recipe is the row's ``bom_no``, else the part's default
    recipe, stocked or not (the service reads them with ``deep``)."""
    bom_name = bom_name or (items.get(item) or {}).get("default_bom")
    if not bom_name or bom_name not in boms:
        return set()
    if bom_name in seen or depth >= DEPTH:
        raise RecipeError(f"{item}'s recipe {bom_name} goes round in a loop or deeper than {DEPTH} recipes")
    out = set()
    for row in boms[bom_name].get("items") or []:
        part = row.get("item_code")
        if part:
            out.add(part)
            out |= recipe_items(part, items, boms, depth + 1, seen + (bom_name,), row.get("bom_no"))
    return out


def variant_gap(item: str, items: dict, allergens: dict) -> str | None:
    """The template a variant left its allergens on: the till reads the item sold, and a field an app adds to Item
    reaches a variant only if the shop's Item Variant Settings copy it."""
    meta = items.get(item) or {}
    tpl = meta.get("variant_of")
    if tpl and not words_of(allergens.get(item)) and words_of(allergens.get(tpl)):
        return tpl
    return None


def unknown_words(text, known: list[str]) -> list[str]:
    """Allergens a field names that are not on the shop's list (a typo would hide an allergen from the check)."""
    k = {w.lower() for w in known}
    return [w for w in words_of(text) if w.lower() not in k] if k else []


# ── answers ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def fit(text: str, most: int = 280) -> str:
    """The extension point's limit on a message's body (280): cut, never refused."""
    return text if len(text) <= most else text[: most - 1] + "…"


def n(k: int, one: str, many: str) -> str:
    return f"{k} {one if k == 1 else many}"


def message(title: str, body: str, level: str = "success", refresh: bool = True) -> dict:
    out = {"message": {"title": title, "body": fit(body or "Nothing to do."), "level": level}}
    if refresh:
        out["refresh"] = True
    return out
