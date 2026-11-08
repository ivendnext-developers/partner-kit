"""S63 — the hotel system, as the service sees it. Every adapter has the same two calls, and this file is where you add yours:

    find(room, guest) -> the reservation's id, or raises NoGuest (with the sentence the server reads)
    post(folio, lines, receipt, currency) -> one reference per line, or raises HotelRefused

``lines`` are ``{"kind", "code", "amount", "label"}``; an amount is negative on a return. Three outcomes of a call that
failed, which the worker treats differently:

    HotelDown      nothing reached the hotel system: the charge waits and is sent again
    HotelLost      it was sent and no answer came: it may be on the folio, so it goes to the auditor, never sent twice
    HotelRefused   the hotel system answered no: it goes to the auditor, with the sentence

The adapter is picked by the store's *Hotel system* row (``ADAPTERS``). Copy ``hotel_mews.py`` for another hotel system.
Standard library only.
"""

from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request

USER_AGENT = "s63-room-charge/1"


class HotelDown(Exception):
    pass


class HotelLost(Exception):
    pass


class HotelRefused(Exception):
    pass


class NoGuest(HotelRefused):
    """The room and name did not match a guest who may charge: the server reads this sentence on the dimmed tile."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # a hotel system's key never travels to another host
        return None


def parse_connection(text: str) -> dict:
    """The store's *Connection* box: one ``name=value`` per line."""
    out = {}
    for line in (text or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


class Deadline:
    """One budget across the calls of one hotel-system question."""

    def __init__(self, seconds: float):
        self.end = time.monotonic() + seconds

    def left(self) -> float:
        left = self.end - time.monotonic()
        if left <= 0.05:
            raise HotelDown("out of time")
        return left


def call_json(url: str, body: dict | None, timeout: float, headers: dict | None = None) -> tuple[int, dict]:
    """(status, answer) for a 2xx or a 4xx. A 5xx, a 429, or no connection is ``HotelDown``; a connection that was made and
    then gave no answer is ``HotelLost``, since the hotel system may have acted on it."""
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET", headers={
        "Accept": "application/json", "Content-Type": "application/json", "User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}") or {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        e.close()
        if e.code >= 500 or e.code in (408, 429):
            raise HotelDown(f"answered {e.code}") from None
        try:
            return e.code, json.loads(raw or b"{}") or {}
        except ValueError:
            return e.code, {}
    except urllib.error.URLError as e:          # the request never got through
        raise HotelDown(type(e.reason).__name__) from None
    except (OSError, http.client.HTTPException, ValueError) as e:       # sent; the answer timed out, was cut or was broken
        raise HotelLost(type(e).__name__) from None


class Simulator:
    """The stand-in in ``standin/hotel_api.py``, so the whole flow runs with no hotel system. Its address is the service's
    own setting (``HOTEL_SIM_URL``), never a value a shop typed."""

    def __init__(self, conf: dict, s: dict, timeout: float):
        self.base, self.timeout = (conf.get("HOTEL_SIM_URL") or "").rstrip("/"), timeout
        if not self.base:
            raise HotelRefused("The simulator is not running here. Pick your hotel system on this store's row.")

    def find(self, room: str, guest: str) -> str:
        try:
            code, out = call_json(f"{self.base}/v1/find", {"room": room, "guest": guest}, self.timeout)
        except HotelLost as e:                  # a question moved nothing: as good as no answer
            raise HotelDown(str(e)) from None
        if code >= 400:
            raise NoGuest(str(out.get("error") or f"Room {room} has no guest named {guest}."))
        return str(out["folio"])

    def post(self, folio: str, lines: list[dict], receipt: str, currency: str) -> list[str]:
        code, out = call_json(f"{self.base}/v1/post", {"folio": folio, "lines": lines, "receipt": receipt, "currency": currency},
                              self.timeout)
        if code >= 400:
            raise HotelRefused(str(out.get("error") or f"The hotel system refused it ({code})."))
        return [str(r) for r in out["references"]]


def adapter(conf: dict, s: dict, timeout: float):
    """The adapter for one store's row."""
    import hotel_mews

    known = {"Simulator": Simulator, "Mews": hotel_mews.Mews}
    if s["system"] not in known:
        raise HotelRefused("This store's hotel system isn't set up yet.")
    return known[s["system"]](conf, s, timeout)
