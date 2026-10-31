"""S40 — *Expiry and recall*: the partner's service behind two Desk buttons and three document checks (standard library only).

    POST /press/block      Block these batches, on a Recall Notice (``desk_action/1``)  → 200 {"message", "refresh"}
    POST /press/worklist   Refresh, on an Expiry Worklist (``desk_action/1``)            → 200 {"message", "refresh"}
    POST /check/receipt    a Purchase Receipt's submit (``doccheck/1``)                  → 200 {"verdict", …}
    POST /check/disposal   a Stock Entry's submit (``doccheck/1``)                       → 200 {"verdict", …}
    POST /check/count      a Stock Reconciliation's submit (``doccheck/1``)              → 200 {"verdict", …}
    GET  /health           200 {"ok": 1}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"): it only answers presses and
checks, and keeps nothing between calls. Each door is signed with its own subscription's secret.

**Block these batches** reads, with the app's own integration user's key, the settings, the notice's lots and the lot
ledger (the bundles that moved them), then sets ``disabled`` on each lot that has an expiry date, and never saves a lot
with none (the shop would write a guessed date into it). It writes onto the notice what it did to each lot, the stock
found per store and, at consumer depth, the customers supplied, fills the clocks from the settings where the notice has
none, and makes or updates one Store Progress record per store holding stock. A repeated press finds the lots blocked
and writes the same tables again. **Refresh** rewrites a worklist's two tables, keeping the action chosen on each lot.
The three checks read items, lots and bundles and answer; they write nothing.

Test-only route, ON ONLY when the process starts with ``PP_TEST_MODES=1`` and the caller sends the ``X-PP-Admin``
token: ``GET /test/received`` returns the last calls as received. A partner's copy deletes it.

ONE SHOP (an env file):
    PP_BASE, PP_KEY, PP_SECRET (the integration user) and the five subscriptions' secrets handed back at install:
    PP_SECRET_BLOCK, PP_SECRET_WORKLIST, PP_SECRET_RECEIPT, PP_SECRET_DISPOSAL, PP_SECRET_COUNT (pp_rcl:sub:block, …);
    PP_ADMIN_TOKEN, PP_PORT (8151)
MANY SHOPS: IVN_LIBRARY_APP (ivendnext_rcl), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
RCL_PREFIX (default PP RCL; IVENDNEXT RCL for the library's app) · PORT (default 8080)

    python3 service/app.py service/.env.local
"""

from __future__ import annotations

import datetime
import hmac
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
import function  # noqa: E402
import recall  # noqa: E402
import oneshop  # noqa: E402
import shops  # noqa: E402
import testcall  # noqa: E402

ROUTES = {"/press/block": "block", "/press/worklist": "worklist", "/check/receipt": "receipt",
          "/check/disposal": "disposal", "/check/count": "count"}                 # route -> the manifest's extension_subscriptions[].key
STALE = "TimestampMismatchError"     # the shop's refusal of a write whose ``modified`` is not the row's own
ENTRY = "`tabSerial and Batch Entry`"   # a bundle's lot rows, read beside the bundle (the record API's child columns)
APP_NAME = "Expiry and recall"
NOT_SET_UP = (f"{APP_NAME} is not set up yet: no key from this shop has reached it. Ask your manager to check that the "
              "app's user has its key and, if the site could not reach the app, or a key was lost or changed, to press Connect again on the app.")
REFUSED = f"{APP_NAME} may not read or change what it needs. Ask your manager to check the app's user and its role."
CONNECT_AGAIN = " Then press Connect again on the app."
NO_SETTINGS = f"{APP_NAME} has no settings yet. Ask your manager to fill the settings record Default."
CHECK_REFUSED = f"{APP_NAME} could not read the lots and items. Ask your manager to check the app's user."


class TenantError(Exception):
    def __init__(self, msg: str, code: int | None = None, kind: str = ""):
        super().__init__(msg)
        self.code, self.kind = code, kind


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # a key never travels to another host
        return None


def _kind(e: urllib.error.HTTPError) -> str:
    try:
        kind = json.loads(e.read(64 * 1024) or b"{}").get("exc_type")
    except (OSError, ValueError, http.client.HTTPException, AttributeError):
        return ""
    return kind if isinstance(kind, str) and kind.isidentifier() else ""


class Tenant:
    """The service's only door into iVendNext: the record API and the v1 wrapper, as the integration user."""

    def __init__(self, base: str, key: str, secret: str, timeout: float = 4):
        self.base, self.timeout, self._auth = base.rstrip("/"), timeout, f"token {key}:{secret}"

    def _open(self, method: str, url: str, body, label: str) -> dict:
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                     headers={"Authorization": self._auth, "Accept": "application/json",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            kind = _kind(e)
            e.close()
            raise TenantError(f"{method} {label} -> HTTP {e.code}", e.code, kind) from None
        except (OSError, ValueError, http.client.HTTPException) as e:
            raise TenantError(f"{method} {label} -> {type(e).__name__}") from None

    def _call(self, method: str, path: str, body: dict | None = None, query: dict | None = None):
        url = f"{self.base}/api/resource/" + "/".join(urllib.parse.quote(p, safe="") for p in path.split("/", 1))
        if query:
            url += "?" + urllib.parse.urlencode({k: json.dumps(v) if not isinstance(v, (str, int)) else v
                                                 for k, v in query.items()})
        out = self._open(method, url, body, path.split("/")[0])
        return out.get("data") if isinstance(out, dict) else None

    def doc(self, doctype: str, name: str) -> dict:
        d = self._call("GET", f"{doctype}/{name}")
        if not isinstance(d, dict):
            raise TenantError(f"GET {doctype} -> an answer with no data")
        return d

    def rows(self, doctype: str, fields: list, filters: list) -> list:
        d = self._call("GET", doctype, query={"fields": fields, "filters": filters, "limit_page_length": 0})
        if not isinstance(d, list):
            raise TenantError(f"GET {doctype} -> an answer with no data")
        return [r for r in d if isinstance(r, dict)]

    def create(self, doctype: str, body: dict) -> dict:
        return self._call("POST", doctype, body) or {}

    def update(self, doctype: str, name: str, body: dict) -> dict:
        return self._call("PUT", f"{doctype}/{name}", body) or {}

    def method(self, name: str, args: dict):
        """A v1 wrapper of the shop (``/api/method/ivendnext_mpos.api.v1.<name>``)."""
        out = self._open("POST", f"{self.base}/api/method/ivendnext_mpos.api.v1.{name}", args, name)
        return out.get("message") if isinstance(out, dict) else None


def tenant_of(url: str, key: str) -> Tenant:
    api_key, _, api_secret = key.partition(":")
    return Tenant(url, api_key, api_secret)


def _warning(body: str) -> dict:
    return recall.message(APP_NAME, body, "warning", refresh=False)


def _chunks(names: list, n: int = 100):
    for i in range(0, len(names), n):
        yield names[i:i + n]


class Service:
    def __init__(self, conf: dict, tenant=None, store=None, tenants=tenant_of, now=None):
        self.app = oneshop.value(conf, oneshop.MANY)
        prefix = (conf.get("RCL_PREFIX") or "").strip()
        if self.app and not prefix:      # the library's names are not the sample's: every read would miss
            raise SystemExit("IVN_LIBRARY_APP is set but RCL_PREFIX is not (IVENDNEXT RCL for the App library's app)")
        recall.use_prefix(prefix or "PP RCL")
        self.tenants, self.now = tenants, now
        if self.app:
            self.store = store or shops.open_store(conf)
        else:
            self.secrets = {k: oneshop.value(conf, f"PP_SECRET_{k.upper()}") for k in ROUTES.values()}
            self.tenant = tenant
        self.admin = conf.get("PP_ADMIN_TOKEN") or ""
        self.test_modes = os.environ.get("PP_TEST_MODES") == "1" and bool(self.admin)
        self.received = []
        self._lock = threading.Lock()

    # ── who is calling ──
    def caller(self, headers, sub: str) -> tuple[list[str], object | None]:
        """(the secrets this door's call may be signed with, the shop's door: None until it handed over a user's key)."""
        if not self.app:
            return [s for s in [self.secrets.get(sub)] if s], self.tenant
        site = shops.site_of(headers.get(shops.SITE_HEADER))
        record = self.store.get(site) if site else None
        secrets = [s.decode() for s in shops.secrets_for(record, f"{self.app}:sub:{sub}")]
        users = sorted(k for k in (record or {}).get("secrets") or {}
                       if k.startswith("user:") and k != "user:Administrator")
        door = self.tenants(record["url"], record["secrets"][users[0]]) if record and users else None
        return secrets, door

    def settings(self, door) -> dict | None:
        try:
            return door.doc(recall.t("Settings"), "Default")
        except TenantError as e:
            if e.code == 404:
                return None
            raise

    def bundle_lots(self, door, bundles: list) -> dict:
        """bundle → {lot: quantity} for the named bundles (any state: a check runs before the document is final)."""
        out = {}
        for part in _chunks(sorted({b for b in bundles if isinstance(b, str) and b})):
            for r in door.rows("Serial and Batch Bundle", ["name", f"{ENTRY}.batch_no", f"{ENTRY}.qty"],
                               [["name", "in", part]]):
                if isinstance(r.get("batch_no"), str) and isinstance(r.get("qty"), (int, float)):
                    lots = out.setdefault(r["name"], {})
                    lots[r["batch_no"]] = lots.get(r["batch_no"], 0.0) + abs(r["qty"])
        return out

    def batches(self, door, names, fields: list) -> dict:
        out = {}
        for part in _chunks(sorted({n for n in names if n})):
            out.update({r["name"]: r for r in door.rows("Batch", ["name", *fields], [["name", "in", part]])
                        if r.get("name")})
        return out

    # ── Block these batches ──
    def block(self, door, fields: dict, notice_name: str) -> dict:
        settings = self.settings(door)
        if settings is None:
            return _warning(NO_SETTINGS)
        lots = recall.lots_of(fields)
        hours = settings.get("hours_from_utc")
        stamp = recall.stamp(recall.now_at(hours, self.now))
        got = self.batches(door, lots, ["item", "expiry_date", "disabled", "modified"])
        # the ledger first: the shop's own lot read returns nothing once a lot is disabled
        entries = door.rows("Serial and Batch Bundle",
                            ["name", "voucher_type", "voucher_no", "warehouse", f"{ENTRY}.batch_no", f"{ENTRY}.qty"],
                            [["Serial and Batch Entry", "batch_no", "in", lots], ["docstatus", "=", 1],
                             ["is_cancelled", "=", 0]])
        codes = sorted({b.get("item") for b in got.values() if b.get("item")})
        items = {}
        for part in _chunks(codes):
            items.update({r["name"]: r for r in door.rows("Item", ["name", "has_expiry_date"], [["name", "in", part]])})
        outcomes, rows = {}, []
        for lot in lots:
            b = got.get(lot)
            outcome = recall.block_outcome(b, items.get((b or {}).get("item")))
            if outcome == "block":
                try:
                    door.update("Batch", lot, {"disabled": 1, "modified": b.get("modified")})
                except TenantError as e:
                    if e.kind == STALE:
                        outcome = "changed"
                    elif e.code in (403, 409, 417):
                        outcome = "refused"
                    else:
                        raise
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            rows.append({"batch": lot, "item": (b or {}).get("item") or "", "outcome": recall.OUTCOME_WORDS[outcome]})
        start, done, depth0 = recall.clocks(fields.get("recall_class"), fields.get("received_on"), settings)
        depth = fields.get("depth") if fields.get("depth") in recall.DEPTHS else (depth0 or "Consumer")
        stock = recall.stock_by_store(entries, lots)
        people = []
        if depth == "Consumer":
            docs = {}
            for vt in recall.SALES:
                names = sorted({r["voucher_no"] for r in entries if r.get("voucher_type") == vt and r.get("voucher_no")})
                cols = ["name", "customer", "customer_name", "posting_date"]
                for part in _chunks(names):
                    docs.update({(vt, r["name"]): r for r in door.rows(vt, cols, [["name", "in", part]])})
            people = recall.customers(entries, docs, lots)
        notice = door.doc(recall.t("Recall Notice"), notice_name)
        body = {"lots": rows, "stock": [{"store": s, "batch": b, "qty": q} for (s, b), q in sorted(stock.items())],
                "traced_on": stamp, "depth": depth, "modified": notice.get("modified")}
        if depth == "Consumer":         # a press at another depth never wipes a trace already made (it may be filed)
            body["customers"] = people
        if outcomes.get("block") or outcomes.get("already"):
            body["status"] = "Blocked" if notice.get("status") in (None, "", "Open") else notice["status"]
            if not notice.get("blocked_on"):
                body["blocked_on"] = stamp
        if not notice.get("start_by") and start:
            body["start_by"] = start
        if not notice.get("complete_by") and done:
            body["complete_by"] = done
        door.update(recall.t("Recall Notice"), notice_name, body)
        self.progress(door, notice_name, {k: q for k, q in stock.items() if k[0] not in recall.quarantines(settings)})
        sold = [p for p in people if p["qty"] > 0]
        return recall.block_answer(outcomes, len({s for s, _ in stock}), len({p["customer"] or p["document"] for p in sold}),
                                   depth, sales=len({(p["document_type"], p["document"]) for p in sold}))

    def progress(self, door, notice: str, stock: dict):
        """One Store Progress record per selling store holding a recalled lot (a quarantine store is where the stock goes,
        not a store to work); a store's found quantity follows the ledger, and what the store wrote (its status, who,
        what it quarantined) is never touched."""
        per = {}
        for (store, _), q in stock.items():
            per[store] = per.get(store, 0.0) + q
        dt = recall.t("Recall Store Progress")
        have = {r["store"]: r for r in door.rows(dt, ["name", "store", "qty_found", "modified"], [["notice", "=", notice]])
                if r.get("store")}
        for store in sorted(set(per) | set(have)):
            q = round(per.get(store, 0.0), 6)
            r = have.get(store)
            if r is None:
                try:
                    door.create(dt, {"notice": notice, "store": store, "qty_found": q, "status": "To do"})
                except TenantError as e:
                    if e.code != 409:       # a second press made it meanwhile
                        raise
            elif r.get("qty_found") != q:
                try:
                    door.update(dt, r["name"], {"qty_found": q, "modified": r.get("modified")})
                except TenantError as e:
                    if e.kind != STALE:     # the store saved it meanwhile; the next press sets the count
                        raise

    # ── Refresh (the worklist) ──
    def refresh(self, door, fields: dict, name: str) -> dict:
        settings = self.settings(door)
        if settings is None:
            return _warning(NO_SETTINGS)
        window = recall.whole(fields.get("window_days")) or recall.whole(settings.get("near_expiry_days")) or 90
        store = fields.get("store") if isinstance(fields.get("store"), str) and fields["store"] else None
        today = recall.today_at(settings.get("hours_from_utc"), self.now)
        cutoff = (today + datetime.timedelta(days=window)).isoformat()
        args = {"for_stock_levels": 1, **({"warehouse": store} if store else {})}
        stock = self.door_stock(door, args)
        cols = ["name", "item", "expiry_date", "disabled", "batch_qty"]
        near = door.rows("Batch", cols, [["expiry_date", "<=", cutoff], ["disabled", "=", 0], ["batch_qty", ">", 0]])
        gaps = door.rows("Batch", cols, [["expiry_date", "is", "not set"]])
        batches = {r["name"]: r for r in near + gaps if r.get("name")}
        codes = sorted({r.get("item") for r in gaps if r.get("item")})
        items = {}
        for part in _chunks(codes):
            items.update({r["name"]: r for r in door.rows("Item", ["name", "has_expiry_date"], [["name", "in", part]])})
        doc = door.doc(recall.t("Expiry Worklist"), name)
        kept = {(r.get("batch"), r.get("store") or ""): r.get("action") for r in doc.get("near") or []
                if isinstance(r, dict) and r.get("action") in recall.ACTIONS[1:]}
        rows, missing = recall.worklist([s for s in stock if s.get("batch_no") in batches], batches, items, store,
                                        window, today, kept)
        recalled = set()        # a lot a recall names stays blocked: the pharmacist enters its date, never enables it
        lot_dt = recall.t("Recall Lot")
        for part in _chunks(sorted({m["batch"] for m in missing})):
            recalled |= {r.get("batch") for r in door.rows(recall.t("Recall Notice"), [f"`tab{lot_dt}`.batch"],
                                                           [[lot_dt, "batch", "in", part]])}
        for m in missing:
            m["recalled"] = 1 if m["batch"] in recalled else 0
        door.update(recall.t("Expiry Worklist"), name, {
            "near": rows, "no_expiry": missing, "window_days": window,
            "refreshed_on": recall.stamp(recall.now_at(settings.get("hours_from_utc"), self.now)),
            "modified": doc.get("modified")})
        where = f" in {store}" if store else ""
        return recall.message("Worklist", f"{len(rows)} lot{'s' if len(rows) != 1 else ''} expire within {window} days"
                              f"{where}. {len(missing)} medicine lot{'s' if len(missing) != 1 else ''} have no expiry "
                              "date.", "success")

    def door_stock(self, door, args: dict) -> list:
        out = door.method("get_batch_qty", args)
        return [r for r in out if isinstance(r, dict)] if isinstance(out, list) else []

    # ── the two checks ──
    def check_receipt(self, door, ctx: dict) -> dict:
        # without the settings the app cannot tell the ERP's user from anyone else: it refuses (the app cannot run),
        # never lets a receipt through unchecked
        settings = self.settings(door)
        if settings is None:
            return {"verdict": "refuse", "reason": recall.fit(NO_SETTINGS)}
        erp = recall.is_erp(ctx.get("user"), settings)
        today = recall.today_at(settings.get("hours_from_utc"), self.now)
        fields = ctx["fields"]
        lines = [x for x in fields.get("items") or [] if isinstance(x, dict)]
        try:
            items = self.items_for_receipt(door, lines)
            bl = self.bundle_lots(door, [x.get("serial_and_batch_bundle") for x in lines])
            names = {x.get("batch_no") for x in lines} | {lot for v in bl.values() for lot in v}
            got = self.batches(door, names, ["expiry_date", "manufacturing_date"])
        except TenantError as e:
            if e.code in (401, 403, 417):
                return recall.receipt_answer([CHECK_REFUSED], erp)
            raise
        return recall.receipt_answer(recall.judge_receipt(fields, items, got, bl, settings, today, erp), erp)

    def _witness_reads(self, door, settings: dict, lines: list):
        """The lots of the lines (bundles and lots) and, under the schedule rule, each item's whole record."""
        bl = self.bundle_lots(door, [x.get(k) for x in lines for k in ("serial_and_batch_bundle",
                                                                        "current_serial_and_batch_bundle")])
        names = {x.get("batch_no") for x in lines} | {lot for v in bl.values() for lot in v}
        got = self.batches(door, names, ["expiry_date", "disabled"])
        docs = {}
        if (settings.get("witness_rule") or recall.WITNESS[0]) == recall.WITNESS[0]:
            for code in sorted({x.get("item_code") for x in lines if x.get("item_code")}):
                docs[code] = door.doc("Item", code)
        return bl, got, docs

    def check_disposal(self, door, ctx: dict) -> dict:
        fields = ctx["fields"]
        lines = [x for x in fields.get("items") or [] if isinstance(x, dict)]
        settings = self.settings(door)
        if settings is None:
            return {"verdict": "refuse", "reason": recall.fit(NO_SETTINGS)}
        erp = recall.is_erp(ctx.get("user"), settings)
        if not erp and not any(x.get("s_warehouse") for x in lines):
            return {"verdict": "allow"}                  # nothing leaves a store: a receipt or opening stock on the Desk
        today = recall.today_at(settings.get("hours_from_utc"), self.now)
        rec_name = fields.get(recall.f("disposal_record"))
        bl, got, docs = self._witness_reads(door, settings, lines)
        record, used, locked = None, {}, True
        if rec_name:
            try:
                record = door.doc(recall.t("Disposal Record"), rec_name)
            except TenantError as e:
                if e.code != 404:
                    raise
            # what earlier submitted entries drew on the same record: one visit covers its lines once
            ent = "`tabStock Entry Detail`"
            earlier = door.rows("Stock Entry", ["name", f"{ent}.item_code", f"{ent}.batch_no", f"{ent}.transfer_qty",
                                                f"{ent}.serial_and_batch_bundle"],
                                [[recall.f("disposal_record"), "=", rec_name], ["docstatus", "=", 1],
                                 ["name", "!=", fields.get("name") or ""]])
            ebl = self.bundle_lots(door, [r.get("serial_and_batch_bundle") for r in earlier])
            for r in earlier:
                line = dict(r, transfer_qty=(r.get("transfer_qty") or 0) * 1000)       # a read is in units
                for lot, q in (recall.lots_on(line, ebl) or {"": recall.stock_qty_of(line)}).items():
                    used[(r.get("item_code"), lot)] = used.get((r.get("item_code"), lot), 0.0) + q
            rule = door.rows("Retail Save Rule", ["name", "enabled", "mode", "states", "locked_fields", "bypass_roles"],
                             [["rule_name", "=", f"{recall.PREFIX} {recall.LOCK_RULE}"]])
            locked = any(recall.lock_holds(r) for r in rule)
        problems = recall.judge_disposal(fields, docs, got, bl, record, settings, today, used, locked)
        if not erp:
            return recall.disposal_answer(problems)
        # the ERP connector's own entry (SAP's receipts and disposals arrive as stock entries, in the background): its
        # incoming lots are judged as a goods receipt and everything is flagged on the entry, never refused
        incoming = [x for x in lines if x.get("t_warehouse") and not x.get("s_warehouse")]
        if incoming:
            items = self.items_for_receipt(door, incoming)
            got2 = self.batches(door, {x.get("batch_no") for x in incoming} | {lot for v in bl.values() for lot in v},
                                ["expiry_date", "manufacturing_date"])
            problems = recall.judge_receipt({"posting_date": fields.get("posting_date"), "items": incoming}, items, got2,
                                            bl, dict(settings, supplier_note_required=0), today, erp=True) + problems
        return recall.erp_stock_answer(problems)

    def items_for_receipt(self, door, lines: list) -> dict:
        items = {}
        for part in _chunks(sorted({x.get("item_code") for x in lines if x.get("item_code")})):
            items.update({r["name"]: r for r in door.rows("Item", [
                "name", "has_expiry_date", "shelf_life_in_days", recall.f("min_shelf_days"),
                recall.f("shelf_life_exempt")], [["name", "in", part]])})
        return items

    def check_count(self, door, ctx: dict) -> dict:
        settings = self.settings(door)
        if settings is None:
            return {"verdict": "refuse", "reason": recall.fit(NO_SETTINGS)}
        lines = [x for x in ctx["fields"].get("items") or [] if isinstance(x, dict)]
        bl, got, docs = self._witness_reads(door, settings, lines)
        today = recall.today_at(settings.get("hours_from_utc"), self.now)
        return recall.disposal_answer(recall.judge_count(ctx["fields"], docs, got, bl, settings, today))

    # ── one call ──
    def call(self, sub: str, headers, raw: bytes) -> tuple[int, dict]:
        try:
            secrets, door = self.caller(headers, sub)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(recall.verify(ts, sig, raw, s, self.now) for s in secrets):
            return 401, {"error": "the signature does not match"}
        if testcall.is_test(headers):               # checked as a real call; the point itself does not run
            return testcall.answer(sub)
        try:
            body = json.loads(raw)
            if sub == "block":
                name, fields, _ = recall.press_of(body, recall.t("Recall Notice"))
                try:
                    recall.lots_of(fields)
                except ValueError:
                    return 200, _warning("Add the lots the regulator names (1 to 100) to the notice, save it, then press "
                                         "again.")
            elif sub == "worklist":
                name, fields, _ = recall.press_of(body, recall.t("Expiry Worklist"))
            else:
                ctx = recall.check_of(body, {"receipt": "Purchase Receipt", "disposal": "Stock Entry",
                                             "count": "Stock Reconciliation"}[sub])
        except ValueError as e:
            return 400, {"error": str(e)}
        if self.test_modes:
            self.received = (self.received + [{"sub": sub, "context": body.get("context")}])[-20:]
        if door is None:
            if sub in ("block", "worklist"):
                return 200, _warning(NOT_SET_UP)
            return 503, {"error": "not connected"}      # the check's declared down answer applies
        try:
            if sub == "block":
                with self._lock:
                    return 200, self.block(door, fields, name)
            if sub == "worklist":
                return 200, self.refresh(door, fields, name)
            if sub == "receipt":
                return 200, self.check_receipt(door, ctx)
            if sub == "count":
                return 200, self.check_count(door, ctx)
            return 200, self.check_disposal(door, ctx)
        except TenantError as e:
            if sub in ("block", "worklist") and e.code in (401, 403):
                return 200, _warning(REFUSED + (CONNECT_AGAIN if self.app else ""))
            if sub in ("block", "worklist") and e.kind == STALE:
                return 200, _warning("The record was changed while the app worked. Reload it and press again.")
            if sub in ("receipt", "disposal", "count") and e.code in (401, 403, 417):     # even the settings: say why, never wait
                return 200, {"verdict": "refuse", "reason": recall.fit(CHECK_REFUSED)}
            # Desk says "did not answer in time. Check the record before you try again": true, a repeat is safe;
            # a check's declared down answer applies
            return 502, {"error": str(e)}

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        if method == "GET":
            return (200, {"ok": 1}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > recall.BODY_MAX:
            return 413, {"error": "too large"}
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(self.store, self.app, path, headers, raw)
        if path in ROUTES:
            return self.call(ROUTES[path], headers, raw)
        return 404, {"error": "not found"}


def _log(log, rid: str, path: str, code: int, t0: float):
    """One line per call: never the body, a customer, a secret or a signature."""
    log.write(json.dumps({"request": rid, "route": path[:40], "status": code, "ms": int((time.monotonic() - t0) * 1000)}) + "\n")
    log.flush()


def make_handler(svc: Service, log=sys.stderr):
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
                if not 0 <= n <= recall.BODY_MAX:
                    code = 413
                    return self._send(413, {"error": "too large"})
                code, out = svc.handle("POST", self.path, self.headers, self.rfile.read(n))
                return self._send(code, out)
            finally:
                _log(log, rid, self.path, code, t0)

        def do_GET(self):
            if self.path == "/test/received" and svc.test_modes and hmac.compare_digest(
                    (self.headers.get("X-PP-Admin") or "").encode(), svc.admin.encode()):
                return self._send(200, {"received": svc.received})
            self._send(*svc.handle("GET", self.path, self.headers, b""))

        def log_message(self, fmt, *args):
            pass

    return Handler


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, dict]:
    t0 = time.monotonic()
    code, out = svc.handle(method, path, headers, raw)
    _log(sys.stdout, (headers.get("X-iVendNext-Request-Id") or "-")[:40], path, code, t0)
    return code, out


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
    if oneshop.many(conf):
        svc = Service(conf)
    elif all(oneshop.value(conf, k) for k in ("PP_BASE", "PP_KEY", "PP_SECRET")):
        svc = Service(conf, Tenant(conf["PP_BASE"], conf["PP_KEY"], conf["PP_SECRET"]))
    else:
        raise SystemExit("set PP_BASE, PP_KEY, PP_SECRET and the five PP_SECRET_* (one shop), or IVN_LIBRARY_APP with a "
                         "store (many shops)")
    srv = ThreadingHTTPServer(("0.0.0.0", int(conf.get("PP_PORT") or conf.get("PORT") or 8151)), make_handler(svc))
    print(f"s40 expiry and recall on :{srv.server_port} ({'many shops, ' + svc.app if svc.app else 'one shop'}, "
          f"prefix {recall.PREFIX}; test modes {'ON' if svc.test_modes else 'off'})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
