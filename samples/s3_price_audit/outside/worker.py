#!/usr/bin/env python3
"""S3 for many shops: every PP_WATCH seconds (default 30), one pass of each connected shop's event feed, each on its own
thread, with that shop's own key, its own threshold and its own handled-events note (standard library only).

The pass loop is S25's (``samples/s25_gift_on_spend/service/worker.py`` @ 4128c03, adapted: the deviation handler of
``service.py`` instead of the gift card rules, and no release pass; a defect there may be a defect here). A shop that
fails is logged (its site and the error's class) and the others go on; a shop still busy from the last pass is skipped,
never run twice at once. ``/health`` answers 503 when no HEALTHY pass (the shops store answered, no shop stuck) has
finished for three minutes, so the platform restarts the service.

A shop's site hands over its integration user's key ("user:<email>": "<api key>:<api secret>") on *Connect again*, once
that user has its key and is chosen on the feed registration (guide chapter 14b). Until then the shop is skipped with
``no_user``. ⚠ ``api_credentials`` takes the first ``user:`` key a shop handed over; the manifest registers one feed user,
so there is one. The note of handled events is only a cache: each deviation is named by its sale line, so the shop
itself refuses a second one after a restart loses the note.

A bound we keep (S25's): the shop client's timeout is per socket read, so a site that answers one byte at a time keeps
its thread busy; after STUCK_S with no event it counts as stuck and /health asks for a restart of the whole service.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE]
import service  # noqa: E402  (puts tools/feed_client on the path)
import feed_client as F  # noqa: E402

PASS_DEADLINE_S = 25
STUCK_S = 900          # a shop's pass that has handled no event for 15 minutes is stuck (a shop catching up is not)
PROGRESS: dict = {}    # site → when its worker last took up an event (monotonic)
HEARTBEAT = [0.0]


class NoUser(Exception):
    """The shop has not handed over its integration user's key yet."""


def api_credentials(record: dict) -> tuple[str, str, str]:
    """(address, key, secret): the integration user's key the shop handed over (S25's ``app.api_credentials``)."""
    users = sorted(k for k in record.get("secrets") or {} if k.startswith("user:"))
    if not users or ":" not in record["secrets"][users[0]]:
        raise NoUser("no_user")
    key, secret = record["secrets"][users[0]].split(":", 1)
    return record["url"], key, secret


def one_pass(api, feed, seen, site: str | None = None, fallback: float = service.DEFAULT_THRESHOLD) -> dict:
    """One shop: its feed, judged at its own threshold (read once, at the first sale of the pass)."""
    handle = service.handler_for(api, lambda: service.threshold_of(api, fallback))

    def handler(ev, db):
        if site is not None:
            PROGRESS[site] = time.monotonic()
        return handle(ev, db)

    return {"feed": F.poll(feed, seen, handler)}


def shop_state(state: str, site: str) -> str:
    path = os.path.join(state, hashlib.sha256(site.encode()).hexdigest()[:16])
    os.makedirs(path, exist_ok=True)
    return path


def open_shop(record: dict):
    base, key, secret = api_credentials(record)
    api = F.Api(base, key, secret)
    return api, F.DoorFeed(api)


def pass_all(store, state: str, log=sys.stdout, opener=open_shop, busy: dict | None = None,
             deadline: float = PASS_DEADLINE_S) -> dict | None:
    busy = {} if busy is None else busy
    out = {}
    try:
        sites = store.sites()
    except Exception as e:                       # noqa: BLE001 — the shops store did not answer: try again next pass
        log.write(json.dumps({"store": type(e).__name__}) + "\n")
        log.flush()
        return None                              # not a pass: /health must not count it

    def one(site):
        try:
            record = store.get(site)
            if not record:
                out[site] = {"error": "gone"}           # disconnected during this pass
                return
            api, feed = opener(record)
            seen = F.Store(os.path.join(shop_state(state, site), "feed.sqlite"))
            try:
                out[site] = one_pass(api, feed, seen, site)["feed"]
            finally:
                seen.db.close()                  # one note per shop per pass: never left open
        except NoUser:
            out[site] = {"error": "no_user"}
        except F.FeedError as e:                 # its status code says which: 401 key, 403 rights, unreachable
            out[site] = {"error": f"FeedError {str(e).split(' ', 1)[0]}"}
        except Exception as e:                   # noqa: BLE001 — one shop's failure never stops the others
            out[site] = {"error": type(e).__name__}
        finally:
            line = out.get(site, {})
            log.write(json.dumps({"site": site, **({"error": line["error"]} if "error" in line else
                                                   {k: line.get(k, 0) for k in ("handled", "failed", "backlog")})}) + "\n")
            log.flush()

    started = []
    for site in sites:
        th, since = busy.get(site) or (None, 0.0)
        if th is not None and th.is_alive():
            out[site] = {"busy": True, "stuck": time.monotonic() - max(since, PROGRESS.get(site, since)) > STUCK_S}
            continue
        th = threading.Thread(target=one, args=(site,), daemon=True)
        busy[site] = (th, time.monotonic())
        th.start()
        started.append(th)
    end = time.monotonic() + deadline
    for th in started:
        th.join(max(0.0, end - time.monotonic()))
    return out


def healthy_pass(out: dict | None) -> bool:
    """A pass counts for /health only when the shops store answered and no shop's pass has gone STUCK_S without an event."""
    return out is not None and not any((v or {}).get("stuck") for v in out.values())


def serve_all(store, conf: dict):
    state, busy = conf.get("PP_STATE") or os.path.join(HERE, "state"), {}
    while True:
        try:
            out = pass_all(store, state, busy=busy)
            if healthy_pass(out):
                HEARTBEAT[0] = time.monotonic()
        except Exception as e:                   # noqa: BLE001 — the worker never dies; /health says when it stalls
            sys.stdout.write(json.dumps({"worker": type(e).__name__}) + "\n")
        time.sleep(float(conf.get("PP_WATCH") or 30))
