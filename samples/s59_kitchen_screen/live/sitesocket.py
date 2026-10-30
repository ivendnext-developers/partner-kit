"""S59 live — one retailer's own live channel, held from a server (standard library only).

The till tells a store's kitchen users ``{"store", "station"}`` on the realtime event ``mpos_station_ticket`` after a
send, a void or a move commits (the kit's ``contracts/pages/station_ticket.md`` §6). The notice carries no ticket; it
only says *read the board again*. It is reached on the site's own socket, from a server:

    the namespace ``/<site>``, signed in with ``Authorization: token <key>:<secret>`` (the app's own user), ``Origin`` the
    site's own address, and a ``Cookie`` with no ``sid`` (the socket refuses a sign-in with no cookie at all).

This client speaks the socket's long-polling transport (engine.io 4, socket.io 5): plain HTTPS requests, which a site's
public edge passes like any other call. One ``Session`` is one connection: the handshake, the namespace's sign-in, then
a loop of long polls (the server answers each within its ping interval, with a ping we answer, or with the notices).
``hold`` runs sessions one after another with a growing pause between them, until told to stop.

⛔ The key travels only in the ``Authorization`` header to the site's own address; it is never printed, logged or put in
an error's words. No redirect is followed (a key never travels to another host).
"""

from __future__ import annotations

import http.client
import json
import random
import threading
import time
import urllib.parse

EVENT = "mpos_station_ticket"
PATH = "/socket.io/"
SEP = "\x1e"                  # engine.io 4: packets in one long-poll body
WAIT_S = 10.0                 # a request that is not a long poll
BACKOFF = (1, 2, 4, 8, 15, 30, 60)   # seconds between sessions, then 60 each time, each ±20%
STEADY_S = 60.0               # a session that lasted this long starts the pause over from the first step
BODY_MAX = 1024 * 1024        # one long poll's answer
STALE_LINE = (http.client.RemoteDisconnected, BrokenPipeError, ConnectionResetError)   # measured on demo-2's edge 10-30


class Lost(Exception):
    """The connection ended: ``why`` is a short reason fit for a log line (never a header, a key or a body)."""

    def __init__(self, why: str, refused: bool = False):
        super().__init__(why)
        self.why, self.refused = why, refused


def _short(text) -> str:
    """A refusal's words from the site, kept to letters, digits and a little punctuation, at most 60 characters."""
    s = "".join(c for c in str(text) if c.isalnum() or c in " .,:'-")
    return " ".join(s.split())[:60]


class Session:
    """One connection to one site's socket. ``on_notice(store, station)`` is called for each notice of the event."""

    def __init__(self, url: str, token: str, on_notice, connect=None, clock=time.monotonic):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("https", "http") or not parts.hostname:
            raise ValueError("a site's address is https://<site>")
        self.scheme, self.host, self.port = parts.scheme, parts.hostname, parts.port
        self.site = parts.hostname.lower()
        self.origin = f"{parts.scheme}://{parts.netloc}"
        self.ns = "/" + self.site
        self._token, self.on_notice, self.clock = token, on_notice, clock
        self._connect = connect or self._new_connection
        self.sid, self.ping_s, self.wait_s, self.cookies = "", 25.0, WAIT_S, {}
        self._polls = self._posts = None

    # ── the transport ──
    def _new_connection(self, timeout: float):
        kind = http.client.HTTPSConnection if self.scheme == "https" else http.client.HTTPConnection
        return kind(self.host, self.port, timeout=timeout)

    def _headers(self, body: bool) -> dict:
        jar = "; ".join(f"{k}={v}" for k, v in sorted(self.cookies.items()))
        h = {"Authorization": f"token {self._token}", "Origin": self.origin, "Accept": "*/*",
             "Cookie": jar or "ivn_live=1", "User-Agent": "ivendnext-kitchen-screen-live/1"}
        if body:
            h["Content-Type"] = "text/plain;charset=UTF-8"
        return h

    def _keep_cookies(self, resp):
        """The edge's own cookies (a load balancer's stickiness), sent back on the next requests; never one named sid."""
        for line in resp.headers.get_all("Set-Cookie") or []:
            pair = line.split(";", 1)[0]
            name, eq, value = pair.partition("=")
            name = name.strip()
            if eq and name and name.lower() != "sid" and len(pair) < 512 and (name in self.cookies or len(self.cookies) < 8):
                self.cookies[name] = value.strip()

    def _request(self, which: str, method: str, query: dict, body: str | None, timeout: float, again: bool = True) -> str:
        conn = getattr(self, which)
        reused = conn is not None
        if conn is None:
            conn = self._connect(timeout)
            setattr(self, which, conn)
        else:
            conn.timeout = timeout
            if getattr(conn, "sock", None) is not None:
                conn.sock.settimeout(timeout)
        path = PATH + "?" + urllib.parse.urlencode(dict({"EIO": "4", "transport": "polling"}, **query))
        try:
            conn.request(method, path, body=body.encode() if body is not None else None,
                         headers=self._headers(body is not None))
            resp = conn.getresponse()
            data = resp.read(BODY_MAX + 1)
        except STALE_LINE:              # the edge closed a kept-alive line while it sat idle: once more on a new one
            self._drop(which)
            if reused and again:
                return self._request(which, method, query, body, timeout, again=False)
            raise Lost(f"{method} line closed") from None
        except (OSError, http.client.HTTPException) as e:     # timeouts, TLS, a dropped line
            self._drop(which)
            raise Lost(f"{method} {type(e).__name__}") from None
        self._keep_cookies(resp)
        if resp.status != 200:          # a redirect is never followed: a key never travels to another host
            self._drop(which)
            raise Lost(f"{method} HTTP {resp.status}", refused=resp.status in (301, 302, 303, 307, 308, 400, 401, 403, 404))
        if len(data) > BODY_MAX:
            self._drop(which)
            raise Lost(f"{method} too large")
        return data.decode("utf-8", "replace")

    def _drop(self, which: str):
        conn = getattr(self, which)
        setattr(self, which, None)
        if conn is not None:
            try:
                conn.close()
            except Exception:           # noqa: BLE001 — closing a broken line
                pass

    def close(self):
        for which in ("_polls", "_posts"):
            self._drop(which)

    def send(self, packet: str):
        self._request("_posts", "POST", {"sid": self.sid}, packet, WAIT_S)

    # ── the protocol ──
    def handshake(self):
        """engine.io's open packet: ``0{"sid", "pingInterval", "pingTimeout", …}``."""
        text = self._request("_polls", "GET", {"t": f"{random.random():.8f}"[2:]}, None, WAIT_S)
        first = text.split(SEP, 1)[0]
        if not first.startswith("0"):
            raise Lost("no open packet")
        try:
            opened = json.loads(first[1:])
            self.sid = str(opened["sid"])
            interval, timeout = int(opened.get("pingInterval", 25000)), int(opened.get("pingTimeout", 20000))
        except (ValueError, KeyError, TypeError, AttributeError):
            raise Lost("a bad open packet") from None
        if not self.sid or len(self.sid) > 100:
            raise Lost("a bad open packet")
        self.ping_s = max(1.0, min(interval / 1000, 120.0))
        self.wait_s = self.ping_s + max(1.0, min(timeout / 1000, 60.0)) + 5

    def sign_in(self):
        """The namespace's sign-in: ``40/<site>,`` → ``40/<site>,{"sid"}`` (in), or ``44/<site>,{"message"}`` (refused)."""
        self.send(f"40{self.ns},")
        deadline = self.clock() + WAIT_S + self.ping_s
        while self.clock() < deadline:
            for packet in self.poll():
                if packet.startswith(f"40{self.ns},"):
                    return
                if packet.startswith(f"44{self.ns},"):
                    try:
                        why = json.loads(packet[len(self.ns) + 3:]).get("message", "")
                    except (ValueError, AttributeError):
                        why = ""
                    raise Lost(_short(self.scrub(str(why))) or "the sign-in", refused=True)
        raise Lost("no answer to the sign-in")

    def scrub(self, text: str) -> str:
        """The site's own words with the key taken out: a site may echo what it refused."""
        for part in sorted({self._token, *self._token.split(":", 1)}, key=len, reverse=True):
            if len(part) >= 4:
                text = text.replace(part, "-")
        return text

    def poll(self) -> list[str]:
        """One long poll: its socket.io packets; a ping answered here, the server's close raised."""
        text = self._request("_polls", "GET", {"sid": self.sid}, None, self.wait_s)
        packets = text.split(SEP)
        if not any(p in ("1", "2") or (p[:1] == "4" and p[2:].startswith(self.ns)) for p in packets):   # an empty answer,
            # an edge's own page ("200 OK", "404 page not found"): never asked again at once
            raise Lost("an answer with no packet")
        out = []
        for packet in packets:
            if packet == "2":
                self.send("3")
            elif packet == "1":
                raise Lost("closed by the site")
            elif packet.startswith("41" + self.ns):
                raise Lost("signed out by the site")
            elif packet and packet[0] == "4":
                out.append(packet)
        return out

    def notice(self, packet: str):
        """``42/<site>,[<ack id>]["mpos_station_ticket", {"store", "station"}]`` → ``on_notice(store, station)``."""
        head = f"42{self.ns},"
        if not packet.startswith(head):
            return
        rest = packet[len(head):].lstrip("0123456789")
        try:
            event = json.loads(rest)
        except ValueError:
            return
        if not (isinstance(event, list) and len(event) >= 2 and event[0] == EVENT and isinstance(event[1], dict)):
            return
        store, station = event[1].get("store"), event[1].get("station")
        if isinstance(store, str) and store and len(store) <= 140:
            self.on_notice(store, station if isinstance(station, str) and len(station) <= 140 else "")

    def run(self, stop: threading.Event, signed_in=None):
        """Handshake, sign in, then poll until ``stop`` or the line is lost (``Lost``)."""
        try:
            self.handshake()
            self.sign_in()
            if signed_in:
                signed_in()
            while not stop.is_set():
                for packet in self.poll():
                    self.notice(packet)
            try:
                self.send(f"41{self.ns},")          # a clean sign-out, then engine.io's close
                self.send("1")
            except Lost:
                pass
        finally:
            self.close()


def hold(make_session, stop: threading.Event, log, clock=time.monotonic, sleep=None, rand=random.random, on_lost=None):
    """Sessions one after another until ``stop``: the pause grows (``BACKOFF``) while sessions keep failing fast, and
    starts over after a session that lasted ``STEADY_S``. ``make_session()`` is called each time, so a key that changed
    (*Connect again*) is the one the next session uses; it returns None when there is no key to use. ``on_lost(e)`` hears
    each ``Lost`` before the pause (the live service learns a site's own name there)."""
    step = 0
    wait = sleep or (lambda s: stop.wait(s))
    while not stop.is_set():
        started = clock()
        try:
            session = make_session()
            if session is None:
                log("no key")
            else:
                session.run(stop, signed_in=lambda: log("signed in"))
                if stop.is_set():
                    log("signed out")
                    return
        except Lost as e:
            log(("refused" if e.refused else "lost") + ": " + e.why)
            if on_lost:
                try:
                    on_lost(e)
                except Exception as f:  # noqa: BLE001 — the next session still runs
                    log("fault: " + type(f).__name__)
        except Exception as e:          # noqa: BLE001 — never a key in the words: the type of the fault only
            log("fault: " + type(e).__name__)
        if clock() - started >= STEADY_S:
            step = 0
        pause = BACKOFF[min(step, len(BACKOFF) - 1)]
        step += 1
        wait(pause * (0.8 + 0.4 * rand()))
