"""Run an app as a function behind CitiXsys's load balancer, paid per call, instead of an always-on container.

A press-only app (a till key, a check before payment, a webhook) only works when it is called. As a function it costs
nothing between calls (guide chapter 14b, *A function or a container*). The app's code does not change: its
``handle(conf, method, path, headers, raw)`` answers both the web server (``app.py``'s ``main``) and this entry.

    lambda_handler = function.entry(lambda: settings(os.environ), handle)     # at the bottom of your app.py

The load balancer hands each request over as an event. This file turns it back into what ``handle`` expects:
  * the body's EXACT bytes, because the signature is computed over them (base64-decoded when the event says so;
    otherwise the text as UTF-8, which is what the shop sent: a JSON body is UTF-8);
  * the headers, found whatever their case (the load balancer gives them in lower case);
and turns ``(status, answer)`` back into the load balancer's response. Settings (and the shops table) are opened once,
on the first call of each copy, and kept while the copy lives.

An app with background work (a feed reader, a daily job) runs as a function too, on a SCHEDULE (app.json ``"schedule"``,
e.g. ``{"pass": "rate(1 minute)"}``, and a ``"timeout"`` of up to 900 seconds): the hosting calls it with
``{"ivn_schedule": "<name>"}`` and this entry hands the name, and the seconds this call has left, to the app's
``scheduled(conf, name, seconds)``. A container's worker skipped a shop whose last pass was still running; across copies
of a function that is a claim in the shops table (``Claimed``), and a container's "once a day" is one too
(``OncePerDay``).
"""

from __future__ import annotations

import base64
import datetime
import json
import time


class Headers:
    """Request headers, looked up without regard to case (as ``http.server`` does)."""

    def __init__(self, raw: dict | None):
        self._h = {str(k).lower(): v for k, v in (raw or {}).items()}

    def get(self, name: str, default=None):
        return self._h.get(name.lower(), default)


def request(event: dict) -> tuple[str, str, Headers, bytes]:
    """(method, path, headers, the body's exact bytes) from the load balancer's event."""
    body = event.get("body") or ""
    raw = base64.b64decode(body) if event.get("isBase64Encoded") else body.encode("utf-8")
    return event.get("httpMethod") or "GET", event.get("path") or "/", Headers(event.get("headers")), raw


def response(status: int, answer: dict) -> dict:
    return {"statusCode": status, "statusDescription": f"{status} {'OK' if status == 200 else 'Error'}",
            "isBase64Encoded": False, "headers": {"Content-Type": "application/json"}, "body": json.dumps(answer)}


def entry(load, handle, scheduled=None):
    """The function's handler: ``load()`` gives the settings once per copy; ``handle`` answers each call, and
    ``scheduled(conf, name, seconds)`` each scheduled run, with the seconds the call has left (an app with no schedule
    passes none)."""
    kept = {}

    def lambda_handler(event, context=None):
        if "conf" not in kept:
            kept["conf"] = load()
        if isinstance(event, dict) and "ivn_schedule" in event:
            name = str(event["ivn_schedule"])
            if scheduled is None:
                print(json.dumps({"schedule": name, "error": "this app has no scheduled entry"}), flush=True)
                return {"schedule": name, "error": "no scheduled entry"}
            started = time.monotonic()
            left = context.get_remaining_time_in_millis() / 1000 if hasattr(context, "get_remaining_time_in_millis") else 900
            out = scheduled(kept["conf"], name, left)
            print(json.dumps({"schedule": name, "seconds": round(time.monotonic() - started, 2),
                              "shops": len(out or {})}), flush=True)
            return {"schedule": name, "shops": len(out or {})}
        method, path, headers, raw = request(event)
        return response(*handle(kept["conf"], method, path, headers, raw))

    return lambda_handler


class Claimed:
    """The shops one scheduled pass may work: each site whose claim ``<kind>|<site>`` this call took in the shops table
    (``store.claim``), so two copies never work one shop at once. ``release(site)`` frees one shop's claim as soon as its
    work ends, so a slow shop never holds the others. A call stopped by its limit leaves the claims of the shops still
    being worked; another call takes them over once they are ``seconds`` old plus a margin, where ``seconds`` is the time
    this call had left when it took them: the copy that took a claim is gone before anyone else may take it, whatever the
    function's timeout. Reads go to the store unchanged."""

    MARGIN_S = 30

    def __init__(self, store, seconds: float, kind: str = "pass", clock=time.time):
        self.store, self.stale_s, self.kind, self.clock, self.taken = store, seconds + self.MARGIN_S, kind, clock, []

    def sites(self) -> list[str]:
        # The claim records its EXPIRY (now + this call's life + the margin) where ``store.claim`` records a time: the
        # store takes a claim over when that value is at most (its own value - stale_s), i.e. once the expiry has
        # passed, so the HOLDER's life decides, never the life of the call that asks.
        expires = self.clock() + self.stale_s
        try:
            for s in self.store.sites():
                if self.store.claim(f"{self.kind}|{s}", expires, self.stale_s):
                    self.taken.append(s)
        except Exception:
            for s in list(self.taken):          # a store error part-way: free what was taken, then fail the pass
                self.release(s)
            self.taken.clear()
            raise
        return list(self.taken)

    def get(self, site: str):
        return self.store.get(site)

    def release(self, site: str) -> None:
        if site in self.taken:
            try:
                self.store.delete(f"{self.kind}|{site}")
            except Exception:            # noqa: BLE001 — a claim left behind goes stale in stale_s
                pass


class OncePerDay:
    """A container's ``last_daily`` (site → the day its daily jobs were last tried), for copies of a function: ``get``
    takes the claim ``daily|<site>|<day>`` and answers None when this call took it (run the jobs) or the day when
    another call already did (skip). Writes are ignored: the claim is the record. Yesterday's claim is removed."""

    def __init__(self, store, now: datetime.datetime, clock=time.time):
        self.store, self.day, self.clock = store, now.date().isoformat(), clock
        self.yesterday = (now.date() - datetime.timedelta(days=1)).isoformat()

    def get(self, site: str, default=None):
        if not self.store.claim(f"daily|{site}|{self.day}", self.clock(), 2 * 86400):
            return self.day
        try:
            self.store.delete(f"daily|{site}|{self.yesterday}")
        except Exception:                # noqa: BLE001 — an old claim left behind is one small row
            pass
        return default

    def __setitem__(self, site: str, day: str) -> None:
        pass
