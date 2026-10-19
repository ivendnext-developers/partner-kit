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
"""

from __future__ import annotations

import base64
import json


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


def entry(load, handle):
    """The function's handler: ``load()`` gives the settings once per copy; ``handle`` answers each call."""
    kept = {}

    def lambda_handler(event, context=None):
        if "conf" not in kept:
            kept["conf"] = load()
        method, path, headers, raw = request(event)
        return response(*handle(kept["conf"], method, path, headers, raw))

    return lambda_handler
