#!/usr/bin/env python3
"""S22 — the service's worker: reads the shop's event feed, and runs the daily jobs (standard library only).

    python3 service/worker.py run   service/.env.local [--watch 30]   # the feed: enrol, earn, take back, verify
    python3 service/worker.py daily service/.env.local                # credit what the return window has closed on,
                                                                      # and move members between tiers

Settings (``service/.env.local``, never committed): PP_BASE (the shop's address), PP_KEY / PP_SECRET (the integration
user's API key — one connected app, one user), PP_STATE (a folder for the handled-events note).

Many shops (``serve_all``, started by app.py when IVN_LIBRARY_APP is set): every PP_WATCH seconds (default 30), one feed
poll for each connected shop, each on its own thread, with that shop's own key and its own handled-events note
(PP_STATE/<site's hash>/), and each shop's daily jobs once a day. A shop that fails is logged (its site and the error's
class) and the others go on; a shop still busy from the last pass is skipped, never run twice at once. The service's
/health answers 503 when no pass has finished for three minutes, so the platform restarts it.

The feed is the event feed's door (``ivendnext_mpos.api.feed``), scoped by the shop to your application's own events,
read with the kit's client (``tools/feed_client``).
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
import feed_client as F  # noqa: E402
import loyalty  # noqa: E402
import receipts  # noqa: E402
from shop import Shop  # noqa: E402

HOUR_OF_DAILY = 2      # the daily jobs run at the first pass after 02:00 UTC
PASS_DEADLINE_S = 25   # a pass waits this long for its shops; a shop still busy is skipped by the next pass


def handle(t, fixed_today: str | None = None):
    """One event → the rule it triggers; every other event (one change writes several) is marked done unread."""

    def handler(ev: dict, _db):
        today = fixed_today or datetime.date.today().isoformat()
        s = loyalty.Settings.load(t)
        label, name = ev["event"], ev["doc_name"]
        if label == "customer.created":
            return loyalty.enrol(t, s, name, today)
        if label in ("sale.booked", "return.booked"):
            return loyalty.on_sale(t, s, name, today)
        if label == "sale.cancelled":
            return loyalty.on_cancel(t, s, name, today)
        if ev["doc_type"] == receipts.DT and not label.endswith(".deleted"):
            return receipts.on_receipt(t, name)
        return None

    return handler


def env(path: str) -> dict:
    out = {}
    for line in open(path):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            out[k] = v
    return out


def shop_state(state: str, site: str) -> str:
    """One shop's own folder: its handled-events note never mixes with another shop's. (The member lock is the
    wallet's, in PP_STATE/locks keyed by customer: one shop's, as Member cash is.)"""
    path = os.path.join(state, hashlib.sha256(site.encode()).hexdigest()[:16])
    os.makedirs(path, exist_ok=True)
    return path


def open_shop(record: dict):
    """(the shop's record API, its feed), with the integration user's key it handed over at connect."""
    import app as service
    base, key, secret = service.api_credentials(record)
    return Shop(base, key, secret), F.DoorFeed(F.Api(base, key, secret))


def pass_all(store, state: str, last_daily: dict, now=None, log=sys.stdout, opener=open_shop, busy: dict | None = None,
             deadline: float = PASS_DEADLINE_S, finished=None) -> dict:
    """One pass over every connected shop, each on its own thread: its feed, then its daily jobs once a day. A shop
    still busy from an earlier pass is skipped, so a slow or stuck shop never holds up another. Returns {site: what
    happened} for the shops that finished within ``deadline`` seconds."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    busy = {} if busy is None else busy
    out = {}
    try:
        sites = store.sites()
    except Exception as e:                       # noqa: BLE001 — the shops store did not answer: try again next pass
        log.write(json.dumps({"store": type(e).__name__}) + "\n")
        log.flush()
        return {}

    def one(site):
        try:
            record = store.get(site)
            if not record:
                return                           # disconnected since the list was read
            t, feed = opener(record)
            seen = F.Store(os.path.join(shop_state(state, site), "feed.sqlite"))
            result = {"feed": F.poll(feed, seen, handle(t))}
            today = now.date().isoformat()
            if now.hour >= HOUR_OF_DAILY and last_daily.get(site) != today:
                last_daily[site] = today         # tried once a day: a job that fails is logged, never rerun every pass
                s = loyalty.Settings.load(t)
                result.update(credited=loyalty.credit_due(t, s, today), moved=loyalty.evaluate_tiers(t, s, today),
                              balances=loyalty.daily_balances(t, s, today))
            out[site] = result
        except Exception as e:                   # noqa: BLE001 — one shop's failure never stops the others
            out[site] = {"error": type(e).__name__}
        said = {k: (v if k == "error" else "done") for k, v in out.get(site, {}).items()}
        refused = [r["refused"] for r in out.get(site, {}).get("moved") or [] if "refused" in r]
        if refused:      # a count and the shop's status codes, never a customer's name (403 on all: no write on Customer)
            said["moved"] = f"{len(refused)} customer(s) refused ({', '.join(str(x) for x in sorted(set(refused)))})"
        log.write(json.dumps({"site": site, **said}) + "\n")
        log.flush()

    def run(site):
        try:
            one(site)
        finally:
            if finished is not None:             # the shop's work is over (the function form frees its claim here)
                finished(site)

    started = []
    for site in sites:
        if busy.get(site) is not None and busy[site].is_alive():
            out[site] = {"busy": True}               # its last pass has not finished: never two at once for one shop
            continue
        busy[site] = threading.Thread(target=run, args=(site,), daemon=True)
        busy[site].start()
        started.append(busy[site])
    end = time.monotonic() + deadline
    for th in started:
        th.join(max(0.0, end - time.monotonic()))
    return out


HEARTBEAT = [0.0]      # the time of the worker's last finished pass (monotonic); /health reads it


def serve_all(store, conf: dict):
    state, last_daily, busy = conf.get("PP_STATE") or os.path.join(HERE, "state"), {}, {}
    while True:
        try:
            pass_all(store, state, last_daily, busy=busy)
            HEARTBEAT[0] = time.monotonic()
        except Exception as e:                   # noqa: BLE001 — the worker never dies; /health says when it stalls
            sys.stdout.write(json.dumps({"worker": type(e).__name__}) + "\n")
        time.sleep(float(conf.get("PP_WATCH") or 30))


def main(argv=None):
    p = argparse.ArgumentParser(description="S22's worker")
    p.add_argument("command", choices=("run", "daily"))
    p.add_argument("env")
    p.add_argument("--today")
    p.add_argument("--watch", type=float)
    a = p.parse_args(argv)
    conf = env(a.env)
    t = Shop(conf["PP_BASE"], conf["PP_KEY"], conf["PP_SECRET"])
    if a.command == "daily":
        today = a.today or datetime.date.today().isoformat()
        s = loyalty.Settings.load(t)
        print(json.dumps({"credited": loyalty.credit_due(t, s, today), "moved": loyalty.evaluate_tiers(t, s, today),
                          "balances": loyalty.daily_balances(t, s, today)}))
        return
    state = conf.get("PP_STATE") or os.path.join(HERE, "state")
    store = F.Store(os.path.join(state, "feed.sqlite"))
    feed = F.DoorFeed(F.Api(conf["PP_BASE"], conf["PP_KEY"], conf["PP_SECRET"]))
    while True:
        print(json.dumps(F.poll(feed, store, handle(t, a.today))), flush=True)
        if not a.watch:
            break
        time.sleep(a.watch)


if __name__ == "__main__":
    main()
