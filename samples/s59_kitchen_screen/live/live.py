#!/usr/bin/env python3
"""S59 live — Kitchen screen's live service (standard library only): a screen hears "read now" within about a second.

The kitchen's screens read their store's board through the service (``service/app.py``) every few seconds. This small
always-on service, a container beside it, makes that a second: it holds each retailer's own live channel (the site's
socket, ``sitesocket.py``) while a screen of that retailer is open, and when the till tells the store's kitchen that a
ticket was sent, voided or moved (``mpos_station_ticket``), it tells that store's open screens to read again at once.

    POST /ksc/live   {"s", "t"} (a screen's link)   →  200 text/event-stream:
                         event: state  data: {"live": true|false}   the store's channel is up (read on notices) or not
                         event: read   data: {}                     read the board now
                         event: again  data: {}                     this line ends: open it again (every LIFE_S)
                         a comment line every HEARTBEAT_S           (the load balancer closes a line idle for 60 s)
                     404 {"state": "unknown"} · 503 {"state": …}     a refused link · the retailer cannot be reached
    GET  /health     200 {"ok": 1}

**The line carries no ticket, no dish and no name: only "read again".** It still admits only a screen's valid link,
checked by the service's own ``Service.opened`` (the link's signature with the retailer's secret, the screen record's
number and what it was made for, the store's row), never a second copy of that check. A line lasts LIFE_S at most, then
the page opens it again and is checked again, so a link made again stops hearing within LIFE_S plus the service's own
SCREEN_KEEP_S (5 minutes 15 seconds).

**The retailer's key.** Each retailer's site hands its keys to the service at connect (the app template's handshake);
they are kept in the service's own table. This service READS that table (the hosting grants it ``GetItem`` on it and
nothing else) and signs in to the site's socket as the app's own user (``app.user_key``, the same user the service
reads the board as). It writes nothing, keeps no second copy, and never prints a key. A key the retailer replaced
(*Connect again*) ends the socket signed in with the old one at the next line admitted for that retailer (within
LIFE_S while a screen is open).

A site's socket is opened when the first screen of that site opens its line, and closed LINGER_S after its last line
ends: a retailer with no screen open costs its socket server nothing. Its namespace is the site's own name, which a
hosted site may give a name other than its address: when the socket refuses the address, the name is read once from
the site's own Desk page (as the app's user) and kept.

Settings (environment): IVN_LIBRARY_APP, KSC_PREFIX, KSC_PAGE_URL (the service's own, as ``service/app.py`` reads them:
the screens' origin is KSC_PAGE_URL's), IVN_SHOPS_TABLE (the service's table, read-only here) or IVN_SHOPS_FILE, PORT.

    python3 live/live.py
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import signal
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "service"))
import app as service  # noqa: E402  — the service's own admission check and key pick, never a copy
import sitesocket  # noqa: E402

HEARTBEAT_S = 20          # well inside the load balancer's 60-second idle limit
LIFE_S = 300              # a line is checked again this often (a link made again stops hearing within it)
LINGER_S = 60             # a site's socket stays this long after its last line, for a page that opens it again
STREAMS_MAX = 2000        # lines one copy holds, every retailer together
SITE_STREAMS_MAX = 300    # … and one retailer's
CONNECTIONS_MAX = STREAMS_MAX + 200   # connections at once, admitted or not (a slow caller holds a thread each)
NAME_RETRY_S = 1800       # a site whose Desk page named no site is read again at most this often
NAME_PAGE = "/app"        # the site's Desk page: its boot data names the site (``"sitename": …``)
NAME_MAX = 4 * 1024 * 1024
_NAME = re.compile(r'sitename\\?"\s*:\s*\\?"([a-z0-9][a-z0-9.-]{0,252})\\?"')


def fingerprint(key: str | None) -> str:
    """A key's short hash, to tell a replaced key from the one a socket signed in with; never logged."""
    return hashlib.sha256((key or "").encode()).hexdigest()[:16]


def log(**fields):
    """One JSON line: never a key, a link or a body."""
    print(json.dumps(fields, sort_keys=True), flush=True)


class Line:
    """One open screen's line: woken to say "read", or that the store's channel came up or went down."""

    def __init__(self, site: str, store: str):
        self.site, self.store = site, store
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self.events: list[tuple[str, dict]] = []

    def tell(self, name: str, data: dict):
        with self._lock:
            if name == "read" and ("read", {}) in self.events:
                return                  # one "read" pending is enough
            self.events = (self.events + [(name, data)])[-8:]
        self._wake.set()

    def take(self, wait_s: float) -> list[tuple[str, dict]]:
        self._wake.wait(wait_s)
        with self._lock:
            out, self.events = self.events, []
            self._wake.clear()
        return out


class Hub:
    """The open lines by retailer and store, and one socket per retailer with a line open."""

    def __init__(self, svc, session=sitesocket.Session, opener=None, clock=time.monotonic):
        self.svc, self.session, self.clock = svc, session, clock
        self.opener = opener or self._open_page
        self._lock = threading.Lock()
        self.lines: dict[str, set] = {}             # site → its open lines
        self.sockets: dict[str, dict] = {}          # site → {"stop", "thread", "live", "idle_since"}
        self.names: dict[str, str] = {}             # site → its socket's namespace, when not its address
        self.name_tried: dict[str, float] = {}      # site → when its Desk page last named no site

    # ── lines ──
    def admit(self, body) -> tuple[int, dict, Line | None]:
        """A screen's line, or the answer that refuses it. The service's own check: never a second copy of it."""
        try:
            site, _door, s, _row = self.svc.opened(body)
        except service._Answer as a:
            return a.code, a.body, None
        except service.TenantError as e:
            if e.code == 404:
                return 404, {"state": "unknown"}, None
            return 503, {"state": "unavailable"}, None
        try:
            key = fingerprint(service.user_key(self.svc.store.get(site)))   # the key the site handed over last
        except Exception:               # noqa: BLE001 — the table did not answer: the socket is left as it is
            key = ""
        with self._lock:
            old = self.sockets.get(site)
            if old and old.get("key") and key and old["key"] != key:   # Connect again replaced it: that socket ends now
                self.sockets.pop(site)["stop"].set()
            mine = self.lines.setdefault(site, set())
            if sum(len(v) for v in self.lines.values()) >= STREAMS_MAX or len(mine) >= SITE_STREAMS_MAX:
                if not mine:
                    self.lines.pop(site, None)
                return 503, {"state": "busy"}, None
            line = Line(site, s["store"])
            mine.add(line)
            sock = self.sockets.get(site)
            live = bool(sock and sock["live"])
            if sock:
                sock["idle_since"] = None
        line.tell("state", {"live": live})
        if not sock:
            self._start(site)
        return 200, {}, line

    def drop(self, line: Line):
        with self._lock:
            mine = self.lines.get(line.site)
            if mine is not None:
                mine.discard(line)
                if not mine:
                    self.lines.pop(line.site, None)
                    if line.site in self.sockets:
                        self.sockets[line.site]["idle_since"] = self.clock()

    def _tell(self, site: str, name: str, data: dict, store: str | None = None):
        with self._lock:
            lines = [ln for ln in self.lines.get(site, ()) if store is None or ln.store == store]
        for ln in lines:
            ln.tell(name, data)

    # ── the retailer's socket ──
    def notice(self, site: str, store: str, station: str):
        """The till told the store's kitchen something changed: that store's open screens read now, no other's."""
        self._tell(site, "read", {}, store)

    def _start(self, site: str):
        stop = threading.Event()
        with self._lock:
            if site in self.sockets:
                return
            self.sockets[site] = entry = {"stop": stop, "live": False, "idle_since": None}

        def said(what: str):
            if self.sockets.get(site) is not entry:     # a socket swept away while it closed: not this site's news now
                return
            up = what == "signed in"
            entry["live"] = up
            self._tell(site, "state", {"live": up})
            if up:                      # notices sent while the channel was down were missed: every screen reads now
                self._tell(site, "read", {})
            log(site=site, socket=what)

        def make():
            record = self.svc.store.get(site)
            key = service.user_key(record)
            if not key:
                return None
            entry["key"] = fingerprint(key)
            sess = self.session(record["url"], key, lambda st, sn: self.notice(site, st, sn))
            if site in self.names:
                sess.ns = "/" + self.names[site]
            return sess

        def lost(e):
            if e.refused and "Invalid namespace" in e.why and site not in self.names \
                    and self.clock() - self.name_tried.get(site, -1e9) >= NAME_RETRY_S:
                name = self.site_name(site)
                if name:
                    self.names[site] = name
                else:                   # not read: not again for a while (the page is large)
                    self.name_tried[site] = self.clock()

        def run():
            sitesocket.hold(make, stop, lambda what: said(what), on_lost=lost)

        entry["thread"] = t = threading.Thread(target=run, name=f"socket {site}", daemon=True)
        t.start()

    def site_name(self, site: str) -> str:
        """The site's own name, read once from its Desk page as the app's user; "" when it cannot be read."""
        try:
            record = self.svc.store.get(site)
            key = service.user_key(record)
            text = self.opener(record["url"], key) if key else ""
        except Exception as e:          # noqa: BLE001 — never a key in the words
            log(site=site, socket="name not read: " + type(e).__name__)
            return ""
        m = _NAME.search(text or "")
        name = m.group(1) if m else ""
        log(site=site, socket="name read" if name else "name not found")
        return name

    @staticmethod
    def _open_page(url: str, key: str) -> str:
        parts = urllib.parse.urlsplit(url)
        kind = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        conn = kind(parts.hostname, parts.port, timeout=15)
        try:
            conn.request("GET", NAME_PAGE, headers={"Authorization": f"token {key}", "Accept": "text/html"})
            r = conn.getresponse()
            if r.status != 200:         # a redirect is never followed: a key never travels to another host
                return ""
            return r.read(NAME_MAX).decode("utf-8", "replace")
        finally:
            conn.close()

    def sweep(self):
        """Close each socket whose retailer has had no line for LINGER_S."""
        now = self.clock()
        with self._lock:
            idle = [s for s, e in self.sockets.items()
                    if not self.lines.get(s) and e["idle_since"] is not None and now - e["idle_since"] >= LINGER_S]
            for s in idle:
                self.sockets.pop(s)["stop"].set()


class Server(ThreadingHTTPServer):
    """One thread a connection, at most ``most`` at once: a connection past them is closed before it is read."""
    daemon_threads = True

    def __init__(self, address, handler_class, most: int = CONNECTIONS_MAX):
        self._slots = threading.BoundedSemaphore(most)
        super().__init__(address, handler_class)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:               # noqa: BLE001 — no thread started: give its slot back
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


def handler(hub: Hub, origin: str, heartbeat_s: float = HEARTBEAT_S, life_s: float = LIFE_S):
    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def _json(self, code: int, body: dict):
            data = json.dumps(body).encode()
            self.send_response(code)
            for k, v in {"Content-Type": "application/json", "Cache-Control": "no-store", "Content-Length": str(len(data)),
                         "X-Content-Type-Options": "nosniff", "Access-Control-Allow-Origin": origin, "Vary": "Origin"}.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.split("?", 1)[0] == "/health":
                return self._json(200, {"ok": 1})
            self._json(404, {"error": "not found"})

        def do_POST(self):
            if self.path.split("?", 1)[0] != "/ksc/live":
                return self._json(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > service.ksc.PAGE_BODY_MAX:
                return self._json(413 if n > 0 else 400, {"state": "unknown"})
            try:
                body = json.loads(self.rfile.read(n))
            except ValueError:
                body = None
            if not isinstance(body, dict) or not isinstance(body.get("s"), str):
                return self._json(400, {"state": "unknown"})
            code, answer, line = hub.admit(body)
            if line is None:
                return self._json(code, answer)
            try:
                self.stream(line)
            finally:
                hub.drop(line)

        def stream(self, line: Line):
            self.send_response(200)
            for k, v in {"Content-Type": "text/event-stream", "Cache-Control": "no-store", "X-Accel-Buffering": "no",
                         "Access-Control-Allow-Origin": origin, "Vary": "Origin", "Connection": "close"}.items():
                self.send_header(k, v)
            self.end_headers()
            self.close_connection = True
            self.connection.settimeout(heartbeat_s + 10)
            ends = time.monotonic() + life_s
            try:
                while True:
                    left = ends - time.monotonic()
                    if left <= 0:
                        self.wfile.write(b"event: again\ndata: {}\n\n")
                        self.wfile.flush()
                        return
                    events = line.take(min(heartbeat_s, left))
                    out = b"".join(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode() for name, data in events)
                    self.wfile.write(out or b": still here\n\n")
                    self.wfile.flush()
            except OSError:             # the screen went away (closed, reloaded, lost its network)
                return

        def log_message(self, fmt, *args):     # the server's own access line; keep it off
            pass

    return Handler


def main():
    conf = dict(os.environ)
    if not (conf.get("IVN_LIBRARY_APP") or "").strip():
        raise SystemExit("set IVN_LIBRARY_APP (and IVN_SHOPS_TABLE or IVN_SHOPS_FILE): the live service reads the retailers "
                         "the service keeps")
    svc = service.Service(conf)
    origin = service.origin_of(svc.page.split("#", 1)[0].rstrip("/") or "")
    if not origin:
        raise SystemExit("KSC_PAGE_URL is where the screens' page is served, like https://kitchen-screen.example.app")
    hub = Hub(svc)
    srv = Server(("0.0.0.0", int(conf.get("PORT") or 8080)), handler(hub, origin))
    stop = threading.Event()

    def sweeper():
        while not stop.wait(15):
            hub.sweep()

    threading.Thread(target=sweeper, name="sweep", daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_: (stop.set(), threading.Thread(target=srv.shutdown, daemon=True).start()))
    log(listening=srv.server_address[1], prefix=service.ksc.PREFIX, screens=origin)
    srv.serve_forever()


if __name__ == "__main__":
    main()
