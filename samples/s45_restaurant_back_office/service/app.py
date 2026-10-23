"""S45 — *Restaurant back office*: the partner's service behind the shop's three Desk buttons (standard library only).

    POST /press/issue      *Issue ingredients* on a company's settings record (``desk_action/1``)
    POST /press/foodcost   *Work out food cost* on a food cost record
    POST /press/allergens  *Check allergens* on the Item list or an item's form
    GET  /health           200 {"ok": 1}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below): it only
answers presses.

**Issue ingredients.** With the app's own integration user's key (that user's rights, never the pressing user's), for
the company whose settings were pressed: it first finishes any issue an earlier press left *Pending*, *Short* or
*Refused* (the stock entry it already made is found by its link, so nothing is booked twice); then it reads the
company's booked till sales from the settings' start date (at most ``days_back`` days back) that no issue of the app
names yet, their lines, the dishes' engine recipes (BOMs, and the recipes inside them), and puts the sales into one
issue per store and day. Each issue is written FIRST, naming its sales (so a sale is never issued twice) and holding
the parts its dishes used; then the shop's own Material Issue of those parts is made and submitted in one call. When
the shop refuses it for want of stock, the service reads the store's stock and names every short part on the issue.
One press at a time per company: the press stamps the settings record with the shop's own ``modified`` check, and a
second press while one runs is told so. A press starts no new store-day after ``BUDGET_S`` and says what is left.

**Work out food cost** fills a food cost record from the shop's own stock ledger, counts and the app's issues.
**Check allergens** reads the ticked items' recipes and allergens and answers in words; it writes nothing.

Test-only routes, ON ONLY when the process starts with ``PP_TEST_MODES=1`` in its environment and the caller sends
the ``X-PP-Admin`` token: ``GET /test/received`` returns the last presses as received. A partner's copy deletes them.

ONE SHOP (an env file):
    PP_BASE, PP_KEY, PP_SECRET (the integration user), PP_SECRET_ISSUE, PP_SECRET_FOODCOST, PP_SECRET_ALLERGENS (handed
    back at install as pp_rbo:sub:issue …), PP_ADMIN_TOKEN, PP_PORT (8145)
MANY SHOPS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_rbo), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
RBO_PREFIX (default PP RBO; IVENDNEXT RBO for the library's app) · PORT (default 8080)

    python3 service/app.py service/.env.local
"""

from __future__ import annotations

import datetime
import http.client
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
KIT = os.path.dirname(os.path.dirname(SAMPLE))
sys.path.insert(0, SAMPLE)
sys.path.append(os.path.join(KIT, "tools", "app_template", "service"))   # the template's handshake, never a copy
import backoffice as bo  # noqa: E402
import function  # noqa: E402
import shops  # noqa: E402

SUBS = {"/press/issue": "issue", "/press/foodcost": "foodcost", "/press/allergens": "allergens"}
STALE = "TimestampMismatchError"     # the shop's refusal of a write whose ``modified`` is not the row's own
SHORT = "NegativeStockError"         # the shop's refusal of an issue it has not the stock for
BUDGET_S = 5.5          # no new store-day is started after this: the shop waits 10 seconds at most, and a hosted
                        # function's cold start (about 2.5 s, APPF run 9) comes before this clock starts
LOCK_S = 60             # a press stamp older than this is a press that died: the hosted function stops at 10 s
MOST_SALES = 400        # sales taken up by one press, oldest first; the rest wait for the next press
CHUNK = 100             # names per read of the sales' lines (the address stays short)
MOST_DAYS = 92          # the longest food cost period one press works out
APP_NAME = "Restaurant back office"
NOT_SET_UP = (f"{APP_NAME} is not set up yet. Ask your manager to choose its user on the app's feed and press "
              "Connect again.")
REFUSED = (f"{APP_NAME} may not read or write what it needs. Ask your manager to check the app's user, its role and its "
           "API key.")
CONNECT_AGAIN = " Then press Connect again on the app."    # many shops: a new key reaches the service only that way
BUSY = "Another press is issuing for this company now. Press Issue ingredients again in a minute."
NO_START = ("Choose Issue sales booked from on this record first: sales booked before that moment are never issued "
            "(set it to when you start, so stock already taken off by hand is not taken off again).")


class TenantError(Exception):
    def __init__(self, msg: str, code: int | None = None, kind: str = "", said: str = ""):
        super().__init__(msg)
        self.code = code            # the shop's HTTP status, when it answered one
        self.kind = kind            # the shop's error type (exc_type)
        self.said = said            # the shop's own words, kept on the app's issue record for the shop to read


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # a key never travels to another host
        return None


def _error_of(e: urllib.error.HTTPError) -> tuple[str, str]:
    """The shop's error type and its own words from its error body (``exc_type``, the last server message)."""
    try:
        body = json.loads(e.read(64 * 1024) or b"{}")
    except (OSError, ValueError, http.client.HTTPException, AttributeError):
        return "", ""
    kind = body.get("exc_type")
    said = ""
    try:
        msgs = json.loads(body.get("_server_messages") or "[]")
        said = json.loads(msgs[-1]).get("message", "") if msgs else ""
    except (ValueError, TypeError, AttributeError, IndexError):
        said = ""
    said = said if isinstance(said, str) else ""
    for tag in ("<b>", "</b>", "<strong>", "</strong>", "<br>"):
        said = said.replace(tag, " " if tag == "<br>" else "")
    return (kind if isinstance(kind, str) and kind.isidentifier() else ""), " ".join(said.split())[:300]


class Tenant:
    """The service's only door into iVendNext: the record API, as the integration user (token key:secret)."""

    def __init__(self, base: str, key: str, secret: str, timeout: float = 3):
        self.base, self.timeout, self._auth = base.rstrip("/"), timeout, f"token {key}:{secret}"

    def _call(self, method: str, path: str, body: dict | None = None, query: dict | None = None) -> dict:
        url = f"{self.base}/api/resource/" + "/".join(urllib.parse.quote(p, safe="") for p in path.split("/", 1))
        if query:
            url += "?" + urllib.parse.urlencode({k: json.dumps(v) if not isinstance(v, (str, int)) else v
                                                 for k, v in query.items()})
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                     headers={"Authorization": self._auth, "Accept": "application/json",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            kind, said = _error_of(e)
            e.close()
            raise TenantError(f"{method} {path.split('/')[0]} -> HTTP {e.code}", e.code, kind, said) from None
        except (OSError, ValueError, http.client.HTTPException) as e:     # OSError holds URLError, timeouts, TLS
            raise TenantError(f"{method} {path.split('/')[0]} -> {type(e).__name__}") from None   # the outcome is unknown

    def _data(self, method: str, path: str, body: dict | None = None, query: dict | None = None, kind=dict):
        try:
            data = self._call(method, path, body, query)["data"]
        except (KeyError, TypeError):
            raise TenantError(f"{method} {path.split('/')[0]} -> an answer with no data") from None
        if not isinstance(data, kind):
            raise TenantError(f"{method} {path.split('/')[0]} -> an answer with no data")
        return data

    def doc(self, doctype: str, name: str) -> dict:
        return self._data("GET", f"{doctype}/{name}")

    def rows(self, doctype: str, fields: list, filters: list, parent: str | None = None) -> list:
        """A list read; a table's rows are read through their record type (``parent``), with its read check."""
        q = {"fields": fields, "filters": filters, "limit_page_length": 0}
        if parent:
            q["parent"] = parent
        return [r for r in self._data("GET", doctype, query=q, kind=list) if isinstance(r, dict)]

    def create(self, doctype: str, body: dict) -> dict:
        return self._data("POST", doctype, body)

    def update(self, doctype: str, name: str, body: dict) -> dict:
        return self._data("PUT", f"{doctype}/{name}", body)


def tenant_of(url: str, key: str) -> Tenant:
    """A shop's door from the key it handed over on Connect again ("<api key>:<api secret>")."""
    api_key, _, api_secret = key.partition(":")
    return Tenant(url, api_key, api_secret)


def _warning(body: str, refresh: bool = False) -> dict:
    return bo.message(APP_NAME, body, "warning", refresh)


def _now_utc(now) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(now() if now else time.time(), datetime.timezone.utc)


class Busy(Exception):
    """Another press holds this company."""


class Service:
    def __init__(self, conf: dict, tenant=None, store=None, tenants=tenant_of, clock=time.monotonic, now=None):
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        prefix = (conf.get("RBO_PREFIX") or "").strip()
        if self.app and not prefix:      # the library's record types are not the sample's: every read would 404
            raise SystemExit("IVN_LIBRARY_APP is set but RBO_PREFIX is not (IVENDNEXT RBO for the App library's app)")
        bo.use_prefix(prefix or "PP RBO")
        self.tenants, self.clock, self.now = tenants, clock, now
        if self.app:                                    # many shops: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one shop, from the settings
            self.secrets = {k: conf[f"PP_SECRET_{k.upper()}"] for k in SUBS.values()}
            self.tenant = tenant
        self.admin = conf.get("PP_ADMIN_TOKEN") or ""
        self.test_modes = os.environ.get("PP_TEST_MODES") == "1" and bool(self.admin)   # environment only
        self.received = []

    def caller(self, headers, sub: str) -> tuple[str, list[str], object | None]:
        """(the shop's name, the secrets its press may be signed with, its door: None until it handed over a user's key)."""
        if not self.app:
            return "-", [self.secrets[sub]], self.tenant
        site = shops.site_of(headers.get(shops.SITE_HEADER))
        record = self.store.get(site) if site else None
        secrets = [s.decode() for s in shops.secrets_for(record, f"{self.app}:sub:{sub}")]
        users = sorted(k for k in (record or {}).get("secrets") or {}
                       if k.startswith("user:") and k != "user:Administrator")    # the site never sends it; nor do we use it
        door = self.tenants(record["url"], record["secrets"][users[0]]) if record and users else None
        return site or "", secrets, door

    # ── the press stamp: one press at a time per company ──
    def _lock(self, door, s: dict) -> str:
        stamp = s.get("run_started") or ""
        try:
            age = (_now_utc(self.now) - datetime.datetime.fromisoformat(stamp)).total_seconds() if stamp else None
        except ValueError:
            age = None
        if age is not None and -LOCK_S < age < LOCK_S:
            raise Busy()
        mine = _now_utc(self.now).isoformat(timespec="seconds")
        try:
            door.update(bo.dt("Settings"), s["name"], {"run_started": mine, "modified": s.get("modified")})
        except TenantError as e:
            if e.kind == STALE:         # another press stamped it first (or someone saved the record a moment ago)
                raise Busy() from None
            raise
        return mine

    def _unlock(self, door, name: str, mine: str):
        try:
            s = door.doc(bo.dt("Settings"), name)
            if s.get("run_started") == mine:
                door.update(bo.dt("Settings"), name, {"run_started": "", "modified": s.get("modified")})
        except TenantError:
            pass                        # the stamp then lapses after LOCK_S

    # ── recipes, read as deep as they go ──
    def _recipes(self, door, codes, items: dict, boms: dict):
        """Fills ``items`` (stock or not, default recipe, stock unit, allergens) and ``boms`` for the dishes ``codes``
        and every part their recipes reach."""
        want = sorted(set(codes) - set(items))
        for _ in range(bo.DEPTH + 2):
            if want:
                for r in door.rows("Item", ["name", "is_stock_item", "default_bom", "stock_uom",
                                            f"{bo.FIELD}_allergens"], [["name", "in", want]]):
                    items[r["name"]] = r
            todo = [b for b in bo.boms_to_read(list(items), items) + bo.bom_rows_to_read(boms, items) if b not in boms]
            if not todo:
                return
            for name in todo:
                try:
                    b = door.doc("BOM", name)
                except TenantError as e:
                    if e.code != 404:
                        raise
                    b = {}
                ok = b.get("docstatus") == 1 and b.get("is_active")
                boms[name] = {"quantity": b.get("quantity") if ok else 0,
                              "items": [{"item_code": r.get("item_code"), "stock_qty": r.get("stock_qty"),
                                         "bom_no": r.get("bom_no")} for r in (b.get("items") or [])] if ok else []}
            want = sorted({r["item_code"] for b in boms.values() for r in b["items"] if r.get("item_code")} - set(items))

    # ── Issue ingredients ──
    def _book(self, door, company: str, issue: dict) -> str:
        """Makes the issue's Material Issue, or says on the issue why not (its ``problem``). Returns its outcome.

        First at the time of the day's last sale; if the shop refuses that for want of stock, once more at the moment it
        books it (stock booked in after the sales, a delivery entered late); only then is the issue Short, naming every
        short part. An issue already Short is tried at that moment straight away."""
        found = door.rows("Stock Entry", ["name"], [[f"{bo.FIELD}_issue", "=", issue["name"]], ["docstatus", "=", 1]])
        if found:                       # an earlier press made it and stopped before it said so
            door.update(bo.dt("Issue"), issue["name"], {"status": "Issued", "stock_entry": found[0]["name"],
                                                        "problem": ""})
            return "issued"
        se = None
        for now in ([True] if issue.get("status") == "Short" else [False, True]):
            try:
                se = door.create("Stock Entry", bo.stock_entry(company, issue, now=now))
                break
            except TenantError as e:
                if e.code is None or e.code in (401, 403) or (e.code >= 500 and e.kind != SHORT):
                    raise               # the outcome is unknown, or the app's user is refused: the next press looks again
                if e.kind == SHORT and not now:
                    continue
                if e.kind == SHORT:
                    parts = issue["parts"]
                    bins = door.rows("Bin", ["item_code", "actual_qty"],
                                     [["warehouse", "=", issue["issue_from"]],
                                      ["item_code", "in", [p["item_code"] for p in parts]]])
                    short = bo.short_of(parts, {b["item_code"]: b.get("actual_qty") for b in bins})
                    why = bo.short_note(short, issue["issue_from"]) if short else \
                        ("Not issued: the shop refused it for want of stock. " + e.said)[:500]
                    door.update(bo.dt("Issue"), issue["name"], {"status": "Short", "problem": why})
                    return "short"
                door.update(bo.dt("Issue"), issue["name"], {"status": "Refused", "problem": (
                    "Not issued: the shop refused the stock entry" + (f": {e.said}" if e.said else f" ({e.kind or e.code}).")
                    + " Fix it, then press Issue ingredients again.")[:500]})
                return "refused"
        door.update(bo.dt("Issue"), issue["name"], {"status": "Issued", "stock_entry": se.get("name"), "problem": ""})
        return "issued"

    def issue(self, door, settings_name: str) -> dict:
        t0 = self.clock()
        try:
            s = door.doc(bo.dt("Settings"), settings_name)
        except TenantError as e:
            if e.code == 404:
                return _warning(f"{settings_name} was not found. Reload the page.")
            raise
        company, start = s.get("company") or settings_name, bo.moment_of(s.get("start_from"))
        if not start:
            return _warning(NO_START)
        try:
            mine = self._lock(door, s)
        except Busy:
            return _warning(BUSY)
        try:
            return self._issue(door, s, company, start, t0)
        finally:
            self._unlock(door, settings_name, mine)

    def _issue(self, door, s: dict, company: str, start: str, t0: float) -> dict:
        out = {"issued": 0, "short": 0, "refused": 0, "nothing": 0, "sales": 0}
        # 1. what an earlier press left
        for old in door.rows(bo.dt("Issue"), ["name"], [["company", "=", company],
                                                        ["status", "in", ["Pending", "Short", "Refused"]]]):
            if self.clock() - t0 > BUDGET_S:
                return self._answer(out, left=True)
            out[self._book(door, company, door.doc(bo.dt("Issue"), old["name"]))] += 1
        # 2. the sales no issue names yet
        today = _now_utc(self.now).date()
        days = int(bo.num(s.get("days_back")) or 7)
        since = max(bo.date_of(start), today - datetime.timedelta(days=days)).isoformat()
        sales = door.rows("POS Invoice", ["name", "posting_date", "posting_time", "owner", "set_warehouse",
                                          "pos_profile", "is_return"],
                          [["company", "=", company], ["docstatus", "=", 1], ["posting_date", ">=", since]])
        claimed = set()
        for r in door.rows(bo.dt("Issue"), ["sales"], [["company", "=", company], ["posting_date", ">=", since]]):
            claimed |= set((r.get("sales") or "").split("\n"))
        sales = sorted((x for x in sales if x.get("name") and x["name"] not in claimed and bo.booked_from(x, start)),
                       key=lambda x: (str(x.get("posting_date")), str(x.get("posting_time")), x["name"]))
        left = len(sales) > MOST_SALES
        sales = sales[:MOST_SALES]
        if not sales:
            return self._answer(out)
        names = [x["name"] for x in sales]
        lines = []
        for i in range(0, len(names), CHUNK):
            lines += door.rows("POS Invoice Item", ["parent", "item_code", "qty", "stock_qty", "net_amount",
                                                    "warehouse"], [["parent", "in", names[i:i + CHUNK]]],
                               parent="POS Invoice")
        profiles = sorted({x["pos_profile"] for x in sales if x.get("pos_profile")})
        stores = {r["name"]: r.get("warehouse") for r in door.rows("POS Profile", ["name", "warehouse"],
                                                                   [["name", "in", profiles]])} if profiles else {}
        items, boms = {}, {}
        self._recipes(door, {ln.get("item_code") for ln in lines if ln.get("item_code")}, items, boms)
        groups = bo.group_lines(sales, lines, items, stores, s.get("day_parts") or [], s.get("kitchen_store") or "")
        for key in sorted(groups, key=lambda k: (k[1], k[0])):
            if self.clock() - t0 > BUDGET_S:
                left = True
                break
            g = groups[key]
            try:
                need, notes = bo.need_of(g, items, boms)
                status = None
            except bo.RecipeError as e:
                need, notes, status = {}, [str(e)], "Refused"
            body = bo.issue_doc(company, g, need, items, notes)
            if status:
                body.update(status=status, problem=f"Not issued: {notes[0]}. Fix the recipe, then press again."[:500])
            if not g["store"] or not g["issue_from"]:
                body.update(status="Refused", problem="Not issued: the sales name no store and the settings no kitchen "
                                                      "store. Choose the kitchen store, then press again.")
            doc = door.create(bo.dt("Issue"), body)      # FIRST: it claims the sales
            out["sales"] += len(g["sales"])
            if body["status"] == "Nothing to issue":
                out["nothing"] += 1
            elif body["status"] == "Refused":
                out["refused"] += 1
            else:
                out[self._book(door, company, dict(body, name=doc.get("name")))] += 1
        return self._answer(out, left)

    @staticmethod
    def _answer(out: dict, left: bool = False) -> dict:
        parts = []
        if out["issued"]:
            parts.append(f"Issued the ingredients of {bo.n(out['issued'], 'store-day', 'store-days')}.")
        if out["short"]:
            parts.append(f"{bo.n(out['short'], 'store-day is', 'store-days are')} short of stock: open the issues "
                         "marked Short.")
        if out["refused"]:
            parts.append(f"{bo.n(out['refused'], 'store-day was', 'store-days were')} refused: open the issues marked "
                         "Refused.")
        if out["nothing"]:
            parts.append(f"{bo.n(out['nothing'], 'store-day', 'store-days')} sold nothing with a recipe.")
        if out["sales"]:
            parts.append(f"{bo.n(out['sales'], 'sale', 'sales')} taken up.")
        if left:
            parts.append("More is waiting: press Issue ingredients again.")
        warn = left or out["short"] or out["refused"]
        return bo.message(APP_NAME, " ".join(parts) or "Nothing new to issue.", "warning" if warn else "success")

    # ── Work out food cost ──
    def foodcost(self, door, name: str) -> dict:
        try:
            fc = door.doc(bo.dt("Food Cost"), name)
        except TenantError as e:
            if e.code == 404:
                return _warning(f"{name} was not found. Reload the page.")
            raise
        company, store = fc.get("company"), fc.get("store")
        a, b = bo.date_of(fc.get("from_date")), bo.date_of(fc.get("to_date"))
        if not (company and store and a and b) or a > b:
            return _warning("Choose the company, the store and a period (From before To) first.")
        if (b - a).days >= MOST_DAYS:
            return _warning(f"Choose a period of at most {MOST_DAYS} days.")
        span = ["between", [a.isoformat(), b.isoformat()]]
        base = [["company", "=", company], ["docstatus", "=", 1], ["posting_date"] + span]
        ours = {r["name"] for r in door.rows("Stock Entry", ["name"], base + [[f"{bo.FIELD}_issue", "is", "set"]])}
        other = {r["name"] for r in door.rows("Stock Entry", ["name"], base + [["purpose", "=", "Material Issue"],
                                                                                [f"{bo.FIELD}_issue", "is", "not set"]])}
        ledger = door.rows("Stock Ledger Entry", ["item_code", "actual_qty", "stock_value_difference", "voucher_type",
                                                  "voucher_no"],
                           [["warehouse", "=", store], ["is_cancelled", "=", 0], ["posting_date"] + span])
        recos = [r["name"] for r in door.rows("Stock Reconciliation", ["name"],
                                              base + [["purpose", "=", "Stock Reconciliation"]])]
        counts = door.rows("Stock Reconciliation Item", ["item_code", "qty", "current_qty", "amount_difference"],
                           [["parent", "in", recos], ["warehouse", "=", store]], parent="Stock Reconciliation") \
            if recos else []
        sold = sum(bo.num(r.get("food_sales")) for r in door.rows(
            bo.dt("Issue"), ["food_sales"], [["company", "=", company], ["issue_from", "=", store],
                                             ["posting_date"] + span]))
        codes = sorted({r["item_code"] for r in ledger + counts if r.get("item_code")})
        uoms = {r["name"]: r.get("stock_uom") for r in door.rows("Item", ["name", "stock_uom"],
                                                                 [["name", "in", codes]])} if codes else {}
        got = bo.food_cost(ledger, ours, other, counts, sold, uoms)
        when = _now_utc(self.now).isoformat(timespec="seconds")
        try:
            door.update(bo.dt("Food Cost"), name, dict(got, worked_out_at=when, modified=fc.get("modified")))
        except TenantError as e:
            if e.kind == STALE:
                return _warning("The record changed while it was worked out. Press Work out food cost again.")
            raise
        if not got["food_sales"]:
            body = (f"No issued sales at {store} in the period, so no percentages. Press Issue ingredients first, "
                    "then work it out again.")
        else:
            body = (f"Food cost at {store}: {got['theoretical_pct']:g}% by recipe and sales, {got['actual_pct']:g}% "
                    f"actual, on sales of {got['food_sales']:,.2f}.")
        return bo.message(APP_NAME, body, "success" if got["food_sales"] else "warning")

    # ── Check allergens ──
    def allergens(self, door, names: list[str]) -> dict:
        items, boms = {}, {}
        self._recipes(door, names, items, boms)
        known = []
        for r in door.rows(bo.dt("Settings"), ["allergens"], []):
            known += [w for w in bo.words_of(r.get("allergens")) if w.lower() not in {k.lower() for k in known}]
        words = {k: v.get(f"{bo.FIELD}_allergens") for k, v in items.items()}
        missing, odd, none, loop = [], [], [], []
        for name in names:
            if name not in items:
                continue
            if not (items[name].get("default_bom") and items[name]["default_bom"] in boms
                    and boms[items[name]["default_bom"]]["items"]):
                none.append(name)
            else:
                try:
                    m, src = bo.allergens_missing(name, items, boms, words)
                except bo.RecipeError:
                    loop.append(name)
                    continue
                if m:
                    missing.append(f"{name} ({', '.join(m)} from {', '.join(src)})")
            for code in [name] + sorted(bo.recipe_items(name, items, boms) if name not in loop + none else []):
                bad = bo.unknown_words(words.get(code), known)
                if bad and code not in [o.split(" (")[0] for o in odd]:
                    odd.append(f"{code} ({', '.join(bad)})")
        parts = []
        if missing:
            parts.append(f"{bo.n(len(missing), 'dish misses', 'dishes miss')} an allergen of its recipe: "
                         + "; ".join(missing) + ".")
        if odd:
            parts.append("Not on your allergen list, check the spelling: " + "; ".join(odd) + ".")
        if loop:
            parts.append(f"Recipe goes round in a loop: {', '.join(loop)}.")
        if none:
            parts.append(f"No recipe to check: {', '.join(none)}.")
        checked = len(names) - len(none) - len(loop)
        if not missing and not odd and checked:
            parts.insert(0, f"{bo.n(checked, 'dish names', 'dishes name')} every allergen of its recipe.")
        return bo.message(APP_NAME, " ".join(parts), "warning" if missing or odd or loop else "success", refresh=False)

    # ── the call ──
    def press(self, path: str, headers, raw: bytes) -> tuple[int, dict]:
        sub = SUBS[path]
        try:
            site, secrets, door = self.caller(headers, sub)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(bo.verify(ts, sig, raw, s) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        try:
            body = json.loads(raw)
            if sub == "issue":
                names = bo.records_of(body, bo.dt("Settings"), most=1)
            elif sub == "foodcost":
                names = bo.records_of(body, bo.dt("Food Cost"), most=1)
            else:
                names = bo.records_of(body, "Item")
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        if self.test_modes:
            self.received = (self.received + [body["context"]])[-20:]
        if door is None:
            return 200, _warning(NOT_SET_UP)
        try:
            if sub == "issue":
                return 200, self.issue(door, names[0])
            if sub == "foodcost":
                return 200, self.foodcost(door, names[0])
            return 200, self.allergens(door, names)
        except TenantError as e:
            if e.code in (401, 403):    # the shop refused the app's user: say so
                return 200, _warning(REFUSED + (CONNECT_AGAIN if self.app else ""))
            # the shop tells the user "did not answer in time. Check the record before you try again": true, because
            # an issue may have been booked; the next press finds it by its link and books nothing twice
            return 502, {"error": str(e)}

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        """One call: (status, answer). The web server below and the function entry both call this."""
        if method == "GET":
            return (200, {"ok": 1}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > bo.BODY_MAX:
            return 413, {"error": "too large"}
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(self.store, self.app, path, headers, raw)
        if path in SUBS:
            return self.press(path, headers, raw)
        return 404, {"error": "not found"}


def _log(log, rid: str, path: str, code: int, t0: float):
    """One line per call: never the body, the context, a secret or a signature."""
    log.write(json.dumps({"request": rid, "route": path[:40], "status": code, "ms": int((time.monotonic() - t0) * 1000)}) + "\n")
    log.flush()


def make_handler(svc: Service, log=sys.stderr):
    lock = threading.Lock()          # one shop served by one process: one press at a time (the stamp guards many)

    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def _send(self, code: int, body: dict):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            t0, rid, code = time.monotonic(), (self.headers.get("X-iVendNext-Request-Id") or "-")[:40], 500
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if not 0 <= n <= bo.BODY_MAX:
                    code = 413
                    return self._send(413, {"error": "too large"})
                raw = self.rfile.read(n)
                with lock:
                    code, out = svc.handle("POST", self.path, self.headers, raw)
                return self._send(code, out)
            finally:
                _log(log, rid, self.path, code, t0)

        def do_GET(self):
            if self.path == "/test/received" and svc.test_modes and self.headers.get("X-PP-Admin") == svc.admin:
                return self._send(200, {"received": svc.received})
            self._send(*svc.handle("GET", self.path, self.headers, b""))

        def log_message(self, fmt, *args):     # the server's own access line carries the path; keep it off
            pass

    return Handler


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, dict]:
    """The function's call: the answer, and one log line."""
    t0 = time.monotonic()
    code, out = svc.handle(method, path, headers, raw)
    _log(sys.stdout, (headers.get("X-iVendNext-Request-Id") or "-")[:40], path, code, t0)
    return code, out


# As a function on CitiXsys hosting (app.json "runs": "function"; guide chapter 14b): settings from the environment.
lambda_handler = function.entry(lambda: Service(dict(os.environ)), handle)


def env(path: str) -> dict:
    out = {}
    for line in open(path):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            out[k] = v
    return out


def main():
    conf = dict(os.environ, **(env(sys.argv[1]) if len(sys.argv) > 1 else {}))
    one = ["PP_BASE", "PP_KEY", "PP_SECRET"] + [f"PP_SECRET_{k.upper()}" for k in SUBS.values()]
    if conf.get("IVN_LIBRARY_APP"):
        svc = Service(conf)
    elif all(conf.get(k) for k in one):
        svc = Service(conf, Tenant(conf["PP_BASE"], conf["PP_KEY"], conf["PP_SECRET"]))
    else:
        raise SystemExit("set " + ", ".join(one) + " (one shop), or IVN_LIBRARY_APP with a store (many shops): the app "
                         "does not start without a way to check a press")
    srv = ThreadingHTTPServer(("0.0.0.0", int(conf.get("PP_PORT") or conf.get("PORT") or 8145)), make_handler(svc))
    print(f"s45 restaurant back office on :{srv.server_port} ({'many shops, ' + svc.app if svc.app else 'one shop'}, "
          f"prefix {bo.PREFIX}; test modes {'ON' if svc.test_modes else 'off'})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
