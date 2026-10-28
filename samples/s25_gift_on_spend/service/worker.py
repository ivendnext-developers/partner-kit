#!/usr/bin/env python3
"""S25 — the service's worker: reads the shop's event feed (issue, void) and releases the cards whose hold has passed,
every pass (standard library only). The pass loop is S22's (``samples/s22_customer_loyalty/service/worker.py`` @ 3546aaf,
adapted: a release pass instead of daily jobs; a defect there may be a defect here).

    python3 service/worker.py run service/.env.local [--watch 30]     # ONE SHOP: the feed, then the releases due

Settings (``service/.env.local``, never committed): PP_BASE (the shop's address), PP_KEY / PP_SECRET (the integration
user's API key — one connected app, one user), PP_STATE (a folder for the handled-events note), GCS_PREFIX
(``PP GCS``; ``IVENDNEXT GCS`` for the library's app).

Many shops (``serve_all``, started by app.py when IVN_LIBRARY_APP is set): every PP_WATCH seconds (default 30), one pass
for each connected shop, each on its own thread, with that shop's own key and its own handled-events note. A shop that
fails is logged (its site and the error's class) and the others go on; a shop still busy from the last pass is skipped,
never run twice at once. The service's /health answers 503 when no HEALTHY pass (the shops store answered, no shop
stuck) has finished for three minutes, so the platform restarts it. The shop's site hands over the key of the app's own
user (the install made it) at connect, after the install or an update; the shop presses *Connect again* only if the key
is lost (guide chapter 14b). ⚠ ``api_credentials`` takes the first ``user:`` key a shop handed over;
S25's manifest registers one feed user, so there is one.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path[:0] = [HERE, os.path.join(KIT, "tools", "feed_client")]
import cards  # noqa: E402
import feed_client as F  # noqa: E402
from shop import Shop  # noqa: E402

PASS_DEADLINE_S = 25
STUCK_S = 900          # a shop's pass that has handled no event for 15 minutes is stuck (a shop catching up is not)


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


PROGRESS: dict = {}    # site → when its worker last took up an event or a release (monotonic): a busy shop making progress is not stuck


def handle(t, clock=now_utc, site: str | None = None):
    """One event → its rule; every other event (one change writes several) is marked done unread."""

    def handler(ev: dict, _db):
        if site is not None:
            PROGRESS[site] = time.monotonic()
        label, name = ev["event"], ev["doc_name"]
        if label == "sale.booked":
            return cards.on_sale(t, cards.load_settings(t), name, clock())
        if label == "return.booked":
            return cards.on_return(t, name)
        if label == "sale.cancelled":
            return cards.on_cancel(t, name)
        return None

    return handler


def one_pass(t, feed, seen, clock=now_utc, site: str | None = None) -> dict:
    """The feed first, then the releases due. A release reads the sale again before it raises a card, so a cancel or a
    return whose own event failed in this pass still stops it."""
    tick = (lambda: PROGRESS.__setitem__(site, time.monotonic())) if site is not None else (lambda: None)
    return {"feed": F.poll(feed, seen, handle(t, clock, site)), "released": cards.release_due(t, clock(), tick)}


def env(path: str) -> dict:
    out = {}
    for line in open(path):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            out[k] = v
    return out


def shop_state(state: str, site: str) -> str:
    path = os.path.join(state, hashlib.sha256(site.encode()).hexdigest()[:16])
    os.makedirs(path, exist_ok=True)
    return path


def open_shop(record: dict):
    import app as service
    base, key, secret = service.api_credentials(record)
    return Shop(base, key, secret), F.DoorFeed(F.Api(base, key, secret))


def pass_all(store, state: str, log=sys.stdout, opener=open_shop, busy: dict | None = None,
             deadline: float = PASS_DEADLINE_S, finished=None, clock=now_utc) -> dict | None:
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
                return
            t, feed = opener(record)
            seen = F.Store(os.path.join(shop_state(state, site), "feed.sqlite"))
            try:
                out[site] = one_pass(t, feed, seen, clock, site)
            finally:
                seen.db.close()                  # one note per shop per pass: never left open
        except Exception as e:                   # noqa: BLE001 — one shop's failure never stops the others
            out[site] = {"error": type(e).__name__}
        log.write(json.dumps({"site": site, **{k: (v if k == "error" else "done") for k, v in out.get(site, {}).items()}}) + "\n")
        log.flush()

    def run(site):
        try:
            one(site)
        finally:
            if finished is not None:             # the shop's work is over (the function form frees its claim here)
                finished(site)

    started = []
    for site in sites:
        th, since = busy.get(site) or (None, 0.0)
        if th is not None and th.is_alive():
            out[site] = {"busy": True, "stuck": time.monotonic() - max(since, PROGRESS.get(site, since)) > STUCK_S}
            continue
        th = threading.Thread(target=run, args=(site,), daemon=True)
        busy[site] = (th, time.monotonic())
        th.start()
        started.append(th)
    end = time.monotonic() + deadline
    for th in started:
        th.join(max(0.0, end - time.monotonic()))
    return out


HEARTBEAT = [0.0]


def healthy_pass(out: dict | None) -> bool:
    """A pass counts for /health only when the shops store answered and no shop's pass has gone STUCK_S without an event: a
    store that never answers, or a shop whose thread hangs, ends in 503 and a restart, never a quiet 200. A shop still
    busy catching up (a backlog after an outage) is not stuck: restarting would not help it and would cut every other
    shop's pass short."""
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


def main(argv=None):
    p = argparse.ArgumentParser(description="S25's worker")
    p.add_argument("command", choices=("run",))
    p.add_argument("env")
    p.add_argument("--watch", type=float)
    a = p.parse_args(argv)
    conf = env(a.env)
    if conf.get("GCS_PREFIX"):
        cards.use_prefix(conf["GCS_PREFIX"].strip())
    t = Shop(conf["PP_BASE"], conf["PP_KEY"], conf["PP_SECRET"])
    state = conf.get("PP_STATE") or os.path.join(HERE, "state")
    os.makedirs(state, exist_ok=True)
    seen = F.Store(os.path.join(state, "feed.sqlite"))
    feed = F.DoorFeed(F.Api(conf["PP_BASE"], conf["PP_KEY"], conf["PP_SECRET"]))
    while True:
        print(json.dumps(one_pass(t, feed, seen), default=str), flush=True)
        if not a.watch:
            break
        time.sleep(a.watch)


if __name__ == "__main__":
    main()
