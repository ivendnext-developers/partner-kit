"""S55 — *Front of house*: the partner's service behind the retailer's five Desk buttons (standard library only).

    POST /press/book     *Book* on a reservation: the table is held when no other booking overlaps it
    POST /press/seat     *Seat* on a reservation or a waiting party: the table's check opens (the open-check door)
    POST /press/noshow   *No-show* on a reservation
    POST /press/cancel   *Cancel booking* on a reservation
    POST /press/change   *Change booking* on a booked reservation: its hold released, so its time or table can change
    GET  /health         200 {"ok": 1}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below): it only
answers presses.

**It never reads a guest.** The guest's name, phone, customer and notes are fields only the host role reads; the app's
own user does not hold it, so the shop's answers carry none of them, and a press sends the record's name only.

**Book** reads the store's other bookings for the table around that day (as the app's own user) and holds the table
when none overlaps: one press at a time per company, by a stamp on the company's settings (the shop's own ``modified``
check, as S45's). **Seat**, under the same stamp, checks the table (no booking due within the party's stay, no open
check unless the store allows a second), THEN writes a fresh key and the exact call on the record, then calls the door's
``check_open`` as the app's user, and only then lifts the stamp: a stored key always means the checks passed. A retry
(a lost answer, a second press) finds the key and sends the same call again: the door returns its first check and
writes nothing twice. A first send the till refuses opened nothing, so its key is cleared; a refused retry keeps its key
(the first send may have opened the check).

Test-only routes, ON ONLY when the process starts with ``PP_TEST_MODES=1`` in its environment and the caller sends
the ``X-PP-Admin`` token: ``GET /test/received`` returns the last presses as received. A partner's copy deletes them.

ONE SHOP (an env file):
    PP_BASE, PP_KEY, PP_SECRET (the app's user), PP_SECRET_BOOK, PP_SECRET_SEAT, PP_SECRET_NOSHOW, PP_SECRET_CANCEL,
    PP_SECRET_CHANGE (handed back at install as pp_foh:sub:book …), PP_ADMIN_TOKEN, PP_PORT (8155)
MANY SHOPS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_foh), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
FOH_PREFIX (default PP FOH; IVENDNEXT FOH for the library's app) · PORT (default 8080)

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
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
KIT = os.path.dirname(os.path.dirname(SAMPLE))
sys.path.insert(0, SAMPLE)
sys.path.append(os.path.join(KIT, "tools", "app_template", "service"))   # the template's handshake, never a copy
import foh  # noqa: E402
import function  # noqa: E402
import shops  # noqa: E402

SUBS = {"/press/book": "book", "/press/seat": "seat", "/press/noshow": "noshow", "/press/cancel": "cancel",
        "/press/change": "change"}
DOOR = "/api/method/ivendnext_mpos.api.v1."     # the till's partner API (its open-check door)
STALE = "TimestampMismatchError"     # the shop's refusal of a write whose ``modified`` is not the row's own
LOCK_S = 60             # a press stamp older than this has lapsed (a press takes seconds; the shop's wait is 10)
APP_NAME = "Front of house"
NOT_SET_UP = (f"{APP_NAME} is not set up yet: no key from your iVendNext has reached it. Ask your manager to check that the "
              "app's user has its key and, if the site could not reach the app, or a key was lost or changed, to press Connect again on the app.")
REFUSED = (f"{APP_NAME} may not read or write what it needs. Ask your manager to check the app's user, its role and its "
           "API key.")
CONNECT_AGAIN = " Then press Connect again on the app."    # many shops: a new key reaches the service only that way
BUSY = "Another press is booking or seating for this company now. Press again in a moment."
RES_FIELDS = ["name", "status", "store", "booking_date", "booking_time", "minutes", "party", "place", "place_label",
              "deposit_sale", "deposit_amount", "check_name", "seat_key", "seat_request", "modified"]
WAIT_FIELDS = ["name", "status", "store", "party", "place", "place_label", "check_name", "seat_key", "seat_request",
               "modified"]
ROW_FIELDS = ["parent", "store", "register", "minutes", "second_check", "no_show_deposit"]
UNASSIGNED = ("ProfileNotAssignedError", "AssignedProfileDisabledError", "DuplicateStoreAssignmentError",
              "StoreAssignmentIncompleteError")
# the refusals the till raises BEFORE it looks the key up: a retry refused by one of these may follow a first send that
# opened the check, so its key is kept; any other refusal comes from the check's own body, so nothing was opened
BEFORE_KEY = UNASSIGNED + ("TableServiceOffError", "PermissionError", "DeviceRequiredError")


class TenantError(Exception):
    def __init__(self, msg: str, code: int | None = None, kind: str = "", said: str = ""):
        super().__init__(msg)
        self.code = code            # the shop's HTTP status, when it answered one
        self.kind = kind            # the shop's error type (exc_type)
        self.said = said            # the shop's own words

    @property
    def refused(self) -> bool:
        """The shop answered and refused: nothing was written (never a lost answer or a fault of the shop's)."""
        return self.code is not None and 400 <= self.code < 500


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
    return (kind if isinstance(kind, str) and kind.isidentifier() else ""), " ".join(said.split())[:200]


class Tenant:
    """The service's only door into iVendNext, as the app's own user (token key:secret): the record API for the app's
    own records, and the till's partner API for the open-check door."""

    def __init__(self, base: str, key: str, secret: str, timeout: float = 4):
        self.base, self.timeout, self._auth = base.rstrip("/"), timeout, f"token {key}:{secret}"

    def _open(self, method: str, url: str, body: dict | None, what: str):
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                     headers={"Authorization": self._auth, "Accept": "application/json",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            kind, said = _error_of(e)
            e.close()
            raise TenantError(f"{method} {what} -> HTTP {e.code}", e.code, kind, said) from None
        except (OSError, ValueError, http.client.HTTPException) as e:     # OSError holds URLError, timeouts, TLS
            raise TenantError(f"{method} {what} -> {type(e).__name__}") from None   # the outcome is unknown

    def _data(self, method: str, path: str, body: dict | None = None, query: dict | None = None, kind=dict):
        url = f"{self.base}/api/resource/" + "/".join(urllib.parse.quote(p, safe="") for p in path.split("/", 1))
        if query:
            url += "?" + urllib.parse.urlencode({k: json.dumps(v) if not isinstance(v, (str, int)) else v
                                                 for k, v in query.items()})
        what = path.split("/")[0]
        try:
            data = self._open(method, url, body, what)["data"]
        except (KeyError, TypeError):
            raise TenantError(f"{method} {what} -> an answer with no data") from None
        if not isinstance(data, kind):
            raise TenantError(f"{method} {what} -> an answer with no data")
        return data

    def doc(self, doctype: str, name: str) -> dict:
        return self._data("GET", f"{doctype}/{name}")

    def rows(self, doctype: str, fields: list, filters: list, parent: str | None = None) -> list:
        q = {"fields": fields, "filters": filters, "limit_page_length": 500}
        if parent:
            q["parent"] = parent
        return [r for r in self._data("GET", doctype, query=q, kind=list) if isinstance(r, dict)]

    def update(self, doctype: str, name: str, body: dict) -> dict:
        return self._data("PUT", f"{doctype}/{name}", body)

    def call(self, verb: str, body: dict | None = None, query: dict | None = None) -> dict:
        """One of the till's open-check verbs; its answer (``message``)."""
        url = self.base + DOOR + verb + ("?" + urllib.parse.urlencode(query) if query else "")
        out = self._open("POST" if body is not None else "GET", url, body, verb)
        msg = out.get("message") if isinstance(out, dict) else None
        if not isinstance(msg, dict):
            raise TenantError(f"{verb} -> an answer with no check")
        return msg


def tenant_of(url: str, key: str) -> Tenant:
    """A shop's door from the key the shop's site handed over ("<api key>:<api secret>")."""
    api_key, _, api_secret = key.partition(":")
    return Tenant(url, api_key, api_secret)


def _warning(body: str, refresh: bool = False) -> dict:
    return foh.message(APP_NAME, body, "warning", refresh)


def _now_utc(now) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(now() if now else time.time(), datetime.timezone.utc)


class Busy(Exception):
    """Another press holds this company."""


class Refusal(Exception):
    """An answer for the host: nothing more is done."""

    def __init__(self, words: str):
        super().__init__(words)
        self.words = words


class Service:
    def __init__(self, conf: dict, tenant=None, store=None, tenants=tenant_of, now=None, new_key=None):
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        prefix = (conf.get("FOH_PREFIX") or "").strip()
        if self.app and not prefix:      # the library's record types are not the sample's: every read would 404
            raise SystemExit("IVN_LIBRARY_APP is set but FOH_PREFIX is not (IVENDNEXT FOH for the App library's app)")
        foh.use_prefix(prefix or "PP FOH")
        self.tenants, self.now = tenants, now
        self.new_key = new_key or (lambda: str(uuid.uuid4()))
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

    # ── the store's row and the press stamp: one Book or Seat at a time per company ──
    def _row(self, door, store: str) -> dict:
        rows = door.rows(foh.dt("Store"), ROW_FIELDS, [["store", "=", store]], parent=foh.dt("Settings"))
        if not rows:
            raise Refusal(f"{store} has no row in {APP_NAME}'s settings yet. Add the store and its register there "
                          "(the register the app's user is given at that store), then press again.")
        return rows[0]

    def _lock(self, door, settings: str) -> tuple[str, datetime.datetime | None]:
        """The press stamp, and the site's own clock at that moment (the settings' new ``modified``)."""
        s = door.doc(foh.dt("Settings"), settings)
        stamp = s.get("run_started") or ""
        try:
            age = (_now_utc(self.now) - datetime.datetime.fromisoformat(stamp)).total_seconds() if stamp else None
        except ValueError:
            age = None
        if age is not None and -LOCK_S < age < LOCK_S:
            raise Busy()
        mine = _now_utc(self.now).isoformat(timespec="seconds")
        try:
            w = door.update(foh.dt("Settings"), settings, {"run_started": mine, "modified": s.get("modified")})
        except TenantError as e:
            if e.kind == STALE:         # another press stamped it first (or someone saved the record a moment ago)
                raise Busy() from None
            raise
        return mine, foh.stamp(w.get("modified"))

    def _unlock(self, door, settings: str, mine: str):
        try:
            s = door.doc(foh.dt("Settings"), settings)
            if s.get("run_started") == mine:
                door.update(foh.dt("Settings"), settings, {"run_started": "", "modified": s.get("modified")})
        except TenantError:
            pass                        # the stamp then lapses after LOCK_S

    def _clash(self, door, r: dict, row: dict, start: datetime.datetime, exclude: str = "") -> str:
        """Words naming the first booking that holds the table over the party's stay, or ``""``."""
        others = door.rows(foh.dt("Reservation"), RES_FIELDS[:9],
                           [["store", "=", r["store"]], ["place", "=", r["place"]],
                            ["booking_date", "in", foh.days_around(start)], ["status", "in", list(foh.HOLDING)]])
        found = foh.clashes(foh.span(start, foh.minutes_of(r, row)), others, {r["store"]: row}, exclude=exclude)
        return foh.clash_words(found[0], r.get("place_label") or r["place"]) if found else ""

    # ── Book ──
    def book(self, door, name: str) -> dict:
        r = door.doc(foh.dt("Reservation"), name)
        if r.get("status") not in foh.OPEN_STATES:
            raise Refusal(f"{name} is {r.get('status')}: only a requested or booked reservation is booked.")
        start = foh.moment(r.get("booking_date"), r.get("booking_time"))
        if start is None or foh.num(r.get("party")) < 1 or not r.get("store"):
            raise Refusal("Fill in the store, the date, the time and the party size, save, then press Book.")
        row = self._row(door, r["store"])
        if not r.get("place"):
            door.update(foh.dt("Reservation"), name, {"status": "Booked", "app_note": ""})
            return foh.message(APP_NAME, f"{name} is booked for {foh.num(r['party'])} at {start:%H:%M} on "
                               f"{start:%d %b}, with no table held yet. Choose a table and press Book again to hold one.")
        mine, _ = self._lock(door, row["parent"])
        try:
            clash = self._clash(door, r, row, start, exclude=name)
            if clash:
                door.update(foh.dt("Reservation"), name, {"status": "Requested", "app_note": ("Not booked: " + clash)[:500]})
                return _warning(f"Not booked: {clash} Choose another table or time, save, then press Book again.",
                                refresh=True)
            door.update(foh.dt("Reservation"), name, {"status": "Booked", "app_note": ""})
        finally:
            self._unlock(door, row["parent"], mine)
        end = foh.span(start, foh.minutes_of(r, row))[1]
        return foh.message(APP_NAME, f"{name} is booked: {r.get('place_label') or r['place']} is held for "
                           f"{foh.num(r['party'])} from {start:%H:%M} to {end:%H:%M} on {start:%d %b}. If you change "
                           "the time, the length or the table, press Book again.")

    # ── Seat ──
    def seat(self, door, doctype: str, name: str) -> dict:
        r = door.doc(doctype, name)
        waiting = doctype == foh.dt("Waitlist Entry")
        if r.get("check_name"):
            return foh.message(APP_NAME, f"{name} is already seated: its check {r['check_name']} is open on the till.")
        if r.get("status") not in (("Waiting", "Table ready") if waiting else foh.OPEN_STATES):
            raise Refusal(f"{name} is {r.get('status')}: it cannot be seated.")
        if not r.get("place") or foh.num(r.get("party")) < 1 or not r.get("store"):
            raise Refusal("Choose the table and the party size, save, then press Seat.")
        row = self._row(door, r["store"])
        if r.get("seat_key") and r.get("seat_request"):
            try:
                req = json.loads(r["seat_request"])     # a retry: the same key and the same call, exactly
            except ValueError:
                req = None
            if isinstance(req, dict):
                return self._open(door, doctype, r, row, req, retry=True)
        mine, now = self._lock(door, row["parent"])
        try:
            now = now or foh.moment(r.get("booking_date"), r.get("booking_time"))
            where = r.get("place_label") or r["place"]
            clash = self._clash(door, r, row, now, exclude=name)
            if clash:
                raise Refusal(f"Not seated: {clash} Seat the party at another table.")
            if not foh.num(row.get("second_check")) and \
                    foh.place_busy(door.call("floor_status", query={"store": r["store"]}), r["place"]):
                raise Refusal(f"Not seated: {where} has an open check. Clear it at a till, or seat the party at another "
                              "table.")
            key = self.new_key()
            req = foh.seat_request(r["store"], row["register"], key, r["place"], name, foh.num(r["party"]),
                                   r.get("deposit_amount") if r.get("deposit_sale") else None)
            try:                        # the key and the exact call, written only once the checks passed
                door.update(doctype, name, {"seat_key": key, "seat_request": json.dumps(req, sort_keys=True),
                                            "modified": r.get("modified")})
            except TenantError as e:
                if e.kind == STALE:     # the record changed since it was read: read it again with the next press
                    raise Busy() from None
                raise
            return self._open(door, doctype, r, row, req, retry=False)
        finally:
            self._unlock(door, row["parent"], mine)

    def _open(self, door, doctype: str, r: dict, row: dict, req: dict, retry: bool) -> dict:
        name = r["name"]
        try:
            check = door.call("check_open", req)
        except TenantError as e:
            if not e.refused:
                raise                   # the outcome is unknown: the key stays, and the next press sends it again
            if not retry or not (e.kind in BEFORE_KEY or e.code == 403):   # nothing was opened: start afresh
                self._clear(door, doctype, name)
                raise Refusal(self._door_words(e, r, row)) from None
            raise Refusal(self._door_words(e, r, row) + " The first Seat may already have opened its check: fix this, "
                          "then press Seat again.") from None
        place = req.get("place") or r["place"]
        door.update(doctype, name, {"status": "Seated", "check_name": check.get("check") or "", "place": place,
                                    "app_note": ""})
        where = (r.get("place_label") or place) if place == r.get("place") else place
        return foh.message(APP_NAME, f"{name} is seated at {where}: its check {check.get('check')} is open on the "
                           f"till for {foh.num(req.get('covers'))} guests.")

    def _clear(self, door, doctype: str, name: str):
        """The key and the call off the record, so the next press starts afresh (only after a refusal: nothing opened)."""
        try:
            door.update(doctype, name, {"seat_key": "", "seat_request": ""})
        except TenantError:
            pass

    @staticmethod
    def _door_words(e: TenantError, r: dict, row: dict) -> str:
        store, register = r["store"], row.get("register")
        if e.kind in UNASSIGNED:
            return (f"Not seated: the app's user is not assigned to register {register} at {store}. In iVendNext Desk, "
                    "give the app's user that store and register (with Is POS User ticked), save, then press again.")
        if e.kind == "TableServiceOffError":
            return f"Not seated: Table Service is off on register {register}. Switch it on in that POS Profile."
        if e.kind == "PermissionError" or e.code == 403:
            return (f"Not seated: the app's user may not open checks at {store}. In iVendNext Desk, give its Retail "
                    "Permission Open Checks: open a check and see the checks.")
        if e.kind == "DeviceRequiredError":
            return "Not seated: the app's user has a till device enrolled. Use a user that never signs in to a till."
        if e.code == 404:
            return "Not seated: this iVendNext has no open checks yet (the till's train T19 or later)."
        return "Not seated: the till refused it" + (f": {e.said}" if e.said else f" ({e.kind or e.code}).")

    # ── No-show and Cancel ──
    def close(self, door, name: str, status: str) -> dict:
        r = door.doc(foh.dt("Reservation"), name)
        if r.get("status") not in foh.OPEN_STATES:
            raise Refusal(f"{name} is {r.get('status')}: only a requested or booked reservation can be marked "
                          f"{status.lower()}.")
        if r.get("seat_key"):
            raise Refusal(f"A Seat for {name} did not finish, so its table's check may be open: press Seat again first.")
        rule = (self._row(door, r["store"]) if r.get("store") else {}).get("no_show_deposit") or "Keep it"
        note = foh.deposit_note(rule, r.get("deposit_sale"), r.get("deposit_amount"), cancelled=status == "Cancelled")
        door.update(foh.dt("Reservation"), name, {"status": status, "app_note": note[:500]})
        return foh.message(APP_NAME, f"{name} is {'a no-show' if status == 'No-show' else 'cancelled'}"
                           + (f"; its table is free again." if r.get("place") else ".") + (f" {note}" if note else ""))

    def change(self, door, name: str) -> dict:
        """Change booking: a booked table's hold released (Requested again), so its time, length or table can be changed
        in the form; Book holds the new one."""
        r = door.doc(foh.dt("Reservation"), name)
        if r.get("status") != "Booked" or r.get("seat_key"):
            raise Refusal(f"{name} is {r.get('status')}: only a booked reservation that is not being seated is changed.")
        door.update(foh.dt("Reservation"), name, {"status": "Requested",
                                                  "app_note": "Changed: its table is no longer held. Press Book again."})
        return foh.message(APP_NAME, f"{name} is Requested again and its table is no longer held. Change the time, the "
                           "length or the table, save, then press Book.")

    # ── the call ──
    def press(self, path: str, headers, raw: bytes) -> tuple[int, dict]:
        sub = SUBS[path]
        try:
            site, secrets, door = self.caller(headers, sub)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(foh.verify(ts, sig, raw, s) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        try:
            body = json.loads(raw)
            kinds = (foh.dt("Reservation"), foh.dt("Waitlist Entry")) if sub == "seat" else (foh.dt("Reservation"),)
            doctype, name = foh.records_of(body, kinds)
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        if self.test_modes:
            self.received = (self.received + [body["context"]])[-20:]
        if door is None:
            return 200, _warning(NOT_SET_UP)
        try:
            if sub == "book":
                return 200, self.book(door, name)
            if sub == "seat":
                return 200, self.seat(door, doctype, name)
            if sub == "change":
                return 200, self.change(door, name)
            return 200, self.close(door, name, "No-show" if sub == "noshow" else "Cancelled")
        except Refusal as e:
            return 200, _warning(e.words, refresh=True)
        except Busy:
            return 200, _warning(BUSY)
        except TenantError as e:
            if e.code in (401, 403):    # the shop refused the app's user: say so
                return 200, _warning(REFUSED + (CONNECT_AGAIN if self.app else ""))
            # the shop tells the user "did not answer in time. Check the record before you try again": true, because a
            # check may have opened; the next Seat sends the same key and the door returns that check
            return 502, {"error": str(e)}

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        """One call: (status, answer). The web server below and the function entry both call this."""
        if method == "GET":
            return (200, {"ok": 1}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > foh.BODY_MAX:
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
                if not 0 <= n <= foh.BODY_MAX:
                    code = 413
                    return self._send(413, {"error": "too large"})
                raw = self.rfile.read(n)
                with lock:
                    code, out = svc.handle("POST", self.path, self.headers, raw)
                return self._send(code, out)
            finally:
                _log(log, rid, self.path, code, t0)

        def do_GET(self):
            admin = (self.headers.get("X-PP-Admin") or "").encode()
            if self.path == "/test/received" and svc.test_modes and hmac.compare_digest(admin, svc.admin.encode()):
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
    srv = ThreadingHTTPServer(("0.0.0.0", int(conf.get("PP_PORT") or conf.get("PORT") or 8155)), make_handler(svc))
    print(f"s55 front of house on :{srv.server_port} ({'many shops, ' + svc.app if svc.app else 'one shop'}, "
          f"prefix {foh.PREFIX}; test modes {'ON' if svc.test_modes else 'off'})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
