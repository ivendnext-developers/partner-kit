"""The STAND-IN CALLER — what the till will do with a remote till key, written by this programme (standard library).

⚠ This grades a caller the PROGRAMME wrote, not the product's remote app key (`remotebtn`), which had not merged
when this caller was written. It follows that key's contract as published at its merge (iVendNext_PWA ``docs/extending/README.md``
§"The remote kind" @ 8fa89980): one hard deadline per call (default 3 s), no redirect followed, a 64 KB cap, the
headers ``X-iVendNext-Timestamp`` / ``X-iVendNext-Signature`` (base64 HMAC-SHA256 over ``<timestamp>.<raw body>``) /
``X-iVendNext-Request-Id``, and every failure refused in words with nothing added to the sale — never a partial
answer. Whatever comes back is judged by the till's REAL
``validate_result``, passed in by the caller (``validate``), so this file never copies the till's rules.

Known differences from the product lane, stated: plain http is allowed (our test bench has no TLS), private
addresses are allowed (the bench calls the machine it runs on), and name resolution is not inside the deadline. The
deadline is WALL-CLOCK once connected: a watchdog shuts the socket at the deadline, so a service that trickles its
headers a byte at a time cannot hold the caller past it (a per-read socket timeout alone could).

    stated_answer(url, secret, payload, label, validate) -> {"state": "result", ...} | {"state": "refused", ...}

``call(..., site=…)`` adds the ``X-iVendNext-Site`` header every call to an app that serves many shops carries (the app
template's handshake, guide chapter 14b), so the app checks the call with that shop's secret.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import json
import socket
import threading
import time
import urllib.parse
import uuid

DEADLINE_S, BODY_CAP = 3.0, 64 * 1024
# The refusal words, as the remote key publishes them (the till's two shipped sentences plus its timeout one).
TIMEOUT = "{0} did not answer in time. Nothing was added to the sale."
COULD_NOT = "{0} could not finish. Nothing was added to the sale."
UNUSABLE = "{0} answered in a way this till cannot use. Nothing was added to the sale."


def sign(secret: bytes, ts: str, body: bytes) -> str:
    return base64.b64encode(hmac.new(secret, ts.encode() + b"." + body, hashlib.sha256).digest()).decode()


def call(url: str, secret: bytes, payload: dict, timeout: float = DEADLINE_S, cap: int = BODY_CAP, site: str | None = None):
    """One POST under ONE wall-clock deadline. Returns (kind, value): ok · timeout · down · http · redirect ·
    oversize · not_json."""
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return "down", "not an http(s) address"
    deadline = time.monotonic() + timeout

    def left() -> float:
        r = deadline - time.monotonic()
        if r <= 0:
            raise TimeoutError("deadline")
        return r

    body = json.dumps(payload, separators=(",", ":")).encode()
    ts = str(int(time.time()))
    headers = {"Content-Type": "application/json; charset=utf-8", "X-iVendNext-Timestamp": ts,
               "X-iVendNext-Signature": sign(secret, ts, body), "X-iVendNext-Request-Id": uuid.uuid4().hex,
               "User-Agent": "iVendNext-POS-AppKey/1 (programme stand-in)"}
    if site:
        headers["X-iVendNext-Site"] = site
    conn_cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(u.hostname, u.port, timeout=left())
    watchdog = None
    try:
        conn.connect()
        sock = conn.sock          # held here: the connection hands its socket to the response on Connection: close
        watchdog = threading.Timer(left(), _shut, (sock,))
        watchdog.daemon = True
        watchdog.start()
        sock.settimeout(left())
        conn.request("POST", u.path or "/", body, headers)
        sock.settimeout(left())
        resp = conn.getresponse()
        if 300 <= resp.status < 400:
            return "redirect", resp.status          # never followed: a redirect must not carry the request on
        if not 200 <= resp.status < 300:
            return "http", resp.status
        got, total = [], 0
        while True:
            if resp.isclosed():      # Python 3.12+ closes the socket once the whole body is read (measured)
                break
            sock.settimeout(left())
            chunk = resp.read1(8192)
            if not chunk:
                break
            total += len(chunk)
            if total > cap:
                return "oversize", total
            got.append(chunk)
        if time.monotonic() >= deadline:      # the watchdog cut the body short: a timeout, never a partial answer
            raise TimeoutError("deadline")
        try:
            return "ok", json.loads(b"".join(got))
        except ValueError:
            return "not_json", total
    except TimeoutError:
        return "timeout", f"no full answer within {timeout:g} s"
    except http.client.HTTPException as e:     # not HTTP at all, or cut off mid-way
        if time.monotonic() >= deadline:
            return "timeout", f"no full answer within {timeout:g} s"
        return "bad_http", type(e).__name__
    except OSError as e:
        if time.monotonic() >= deadline:
            return "timeout", f"no full answer within {timeout:g} s"
        return "down", type(e).__name__
    finally:
        if watchdog:
            watchdog.cancel()
        conn.close()


def _shut(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def stated_answer(url, secret, payload, label, validate, timeout=DEADLINE_S, cap=BODY_CAP) -> dict:
    """The point's stated answer: a validated result, or a refusal in words (``why`` is for the log only)."""
    kind, value = call(url, secret, payload, timeout, cap)
    if kind == "timeout":
        return {"state": "refused", "detail": TIMEOUT.format(label), "why": f"{kind}: {value}"}
    if kind in ("down", "http", "redirect"):
        return {"state": "refused", "detail": COULD_NOT.format(label), "why": f"{kind}: {value}"}
    if kind != "ok":
        return {"state": "refused", "detail": UNUSABLE.format(label), "why": f"{kind}: {value}"}
    clean, reason = validate(value, payload["returns"])
    if clean is None:
        return {"state": "refused", "detail": UNUSABLE.format(label), "why": f"validate_result: {reason}"}
    return {"state": "result", "label": label, **clean}
