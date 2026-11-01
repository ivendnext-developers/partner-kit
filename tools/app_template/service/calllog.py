"""One log line per call, in the words the app's *Logs* screen shows:

    14:31 retailer.ivendnext.com · a check at Pay · answered in 0.31 s · sale POS-0001

Each line is JSON, so a log reader can filter it, and carries: ``at`` (UTC, to the second), ``site`` (the site that
called, or ``-`` for a one-shop service), ``point`` (the connection point in plain words, then its key), ``outcome``
(``answered``, ``test``, ``refused``, ``not found``, ``failed``), ``seconds``, ``record`` (the sale the call was
about, by its number, when the call names one), ``request`` (the site's request id) and ``status``. ``text`` is the line as *Logs*
shows it. Never the body, the context, a secret or a signature. Standard library only.
"""
from __future__ import annotations

import datetime
import json

# A connection point's kind, in the words a person reads ("a connection point is a place where a site calls the app")
PLAIN = {"check": "a check at Pay", "capture": "a question at the till", "remote_key": "a till key",
         "webhook": "a notice of each sale", "feed": "new sales and customers from your site", "module": "a module at the till",
         "page": "a page in Desk"}
OUTCOMES = {200: "answered", 401: "refused", 403: "refused", 404: "not found"}


def plain(kind: str, key: str = "") -> str:
    words = PLAIN.get(kind, kind or "a call")
    return f"{words} ({key})" if key else words


def outcome(status: int, test: bool = False) -> str:
    if status == 200 and test:
        return "test"
    return OUTCOMES.get(status, "failed" if status >= 400 else "answered")


def record_of(context) -> str | None:
    """The record a call was about: the sale's own number (``name``, ``invoice``, ``sale``), and nothing else. Never the
    customer, an item or any other value of the shop's: the log carries no shop data."""
    if not isinstance(context, dict):
        return None
    for key in ("name", "invoice", "sale"):
        v = context.get(key)
        if isinstance(v, str) and v.strip():
            return f"sale {v.strip()[:80]}"
    return None


def line(site: str | None, point: str, status: int, seconds: float, record: str | None = None, request: str = "-",
         test: bool = False, now: datetime.datetime | None = None) -> str:
    at = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = outcome(status, test)
    parts = [at[11:16], site or "-", point, f"{out} in {seconds:.2f} s" if status == 200 else out]
    if record:
        parts.append(record)
    return json.dumps({"at": at, "site": site or "-", "point": point, "outcome": out, "seconds": round(seconds, 3),
                       "record": record, "request": request, "status": status, "text": " · ".join(parts)})
