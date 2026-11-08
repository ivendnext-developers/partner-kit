"""S63 — after the sale: the event feed says a sale booked; the worker posts its Room Charge share to the guest's folio.

Per shop, each pass (a hosted function: once a minute; the container: every PP_WATCH seconds, default 30):
  1. any row still *Sending* from an earlier pass stopped mid-call, so it goes to the auditor;
  2. the feed: ``sale.booked`` and ``return.booked`` write a row and post it; ``sale.cancelled`` lands on *Refused*;
  3. the rows *Waiting* are sent again, oldest first.

ONCE PER SALE. The ``PP RMC Post`` row is NAMED by the invoice and written *Sending* before the hotel system is called. A
second delivery of the event fails on the name and calls nobody. All state is that row: the service keeps none.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path[:0] = [HERE, os.path.join(KIT, "tools", "feed_client")]
import feed_client as F  # noqa: E402
import hotel as H  # noqa: E402
import rooms  # noqa: E402
from shop import Duplicate, ShopError  # noqa: E402

PASS_DEADLINE_S = 50
POST_TIMEOUT_S = 10
WANTED = ("sale.booked", "return.booked", "sale.cancelled")
LOST = "Sent, and the hotel system never answered. Check the folio: post it by hand if it isn't there."
STOPPED = "We stopped while sending this. Check the folio: post it by hand if it isn't there."
DOWN = "The hotel system isn't answering. We keep trying."


class Pass:
    """One pass over one shop."""

    def __init__(self, svc, t, feed):
        self.svc, self.t, self.feed = svc, t, feed
        self.table = f"{svc.prefix} Post"
        self.stores = svc.settings(t)
        self.count = {"posted": 0, "waiting": 0, "refused": 0}

    def write(self, name: str, status: str, **fields):
        self.t.update(self.table, name, dict(fields, status=status))
        key = status.lower()
        if key in self.count:
            self.count[key] += 1

    def send(self, row: dict) -> None:
        """One row, already written *Sending*, to the hotel system."""
        name, s = row["name"] if "name" in row else row["sale"], self.stores.get(row["store"])
        if not s:
            return self.write(name, "Refused", message="This store has no row in the app's settings.")
        if row.get("return_of"):
            state, why = rooms.return_gate(self.t.get(self.table, row["return_of"]))
            if state != "go":
                return self.write(name, state, message=why)
        try:
            hotel = H.adapter(self.svc.conf, s, POST_TIMEOUT_S)
            folio = row.get("folio") or self.folio_for(row, hotel)
            refs = hotel.post(folio, rooms.lines_of(row, s), name, row["currency"])
        except H.HotelDown:
            return self.write(name, "Waiting", message=DOWN)
        except H.HotelLost:
            return self.write(name, "Refused", message=LOST)
        except H.HotelRefused as e:
            return self.write(name, "Refused", message=rooms.plain(str(e), 280))
        self.write(name, "Posted", folio=folio, charge_reference=refs[0], tip_reference=refs[1] if len(refs) > 1 else "",
                   message="")

    def folio_for(self, row: dict, hotel) -> str:
        """A blank Folio (the cashier's Yes while the hotel system was down, or the service was down): the return's sale's
        own folio, else looked up now from the Room and Guest."""
        if row.get("return_of"):
            first = self.t.get(self.table, row["return_of"])
            if first and first.get("folio"):
                return first["folio"]
        if not row.get("room") or not row.get("guest"):
            raise H.HotelRefused("No room and guest on the sale.")
        return hotel.find(row["room"], row["guest"])

    def booked(self, name: str) -> None:
        inv = self.t.get("POS Invoice", name)
        if not inv or inv.get("docstatus") != 1:
            return
        s = self.stores.get(inv.get("set_warehouse") or "")
        work = rooms.work_of(inv, s) if s else None
        if not work:
            return
        try:
            self.t.insert({"doctype": self.table, **work})
        except Duplicate:               # delivered twice: the first delivery owns this sale
            return
        self.send(work)

    def cancelled(self, name: str) -> None:
        row = self.t.get(self.table, name)
        said = "Cancelled in Desk."
        if row:
            if row["status"] == "Posted":
                said += f" The charge is on the folio ({row.get('charge_reference')}): take it off there."
            return self.write(name, "Refused", message=said)
        inv = self.t.get("POS Invoice", name)
        s = self.stores.get((inv or {}).get("set_warehouse") or "")
        work = rooms.work_of(inv, s) if inv and s else None
        if work:
            try:
                self.t.insert({"doctype": self.table, **work, "status": "Refused", "message": said})
                self.count["refused"] += 1
            except Duplicate:
                pass

    def read_feed(self) -> None:
        page = None
        while True:
            events, page, _ = self.feed.events(100, page)
            ok = []
            for ev in events:
                try:
                    if ev.get("doc_type") == "POS Invoice" and ev.get("event") in WANTED:
                        (self.cancelled if ev["event"] == "sale.cancelled" else self.booked)(ev["doc_name"])
                    ok.append(ev["id"])
                except Exception as e:          # noqa: BLE001 — the event stays undone, with a note, for the next pass
                    self.feed.failed(ev["id"], F.explain(e))
            self.feed.done(ok)
            if page is None:
                return

    def rows(self, status: str) -> list[dict]:
        return self.t.list(self.table, [["status", "=", status]],
                           ["name", "sale", "store", "room", "guest", "folio", "currency", "amount", "tip", "return_of"])

    def run(self) -> dict:
        for row in self.rows("Sending"):        # a pass that stopped mid-call: it may be on the folio
            self.write(row["name"], "Refused", message=STOPPED)
        self.read_feed()
        for row in self.rows("Waiting"):
            self.t.update(self.table, row["name"], {"status": "Sending"})
            self.send(row)
        return self.count


def one_pass(svc, who: dict) -> dict:
    t = svc.shop(who, timeout=20)
    return Pass(svc, t, F.DoorFeed(F.Api(who["url"], who["key"], who["secret"]))).run()


def pass_all(svc, store=None, log=sys.stdout, deadline: float = PASS_DEADLINE_S, finished=None, busy: dict | None = None) -> dict:
    """One pass over every connected shop, each on its own thread, so a slow shop never holds up another."""
    out, busy = {}, ({} if busy is None else busy)
    if not svc.app:
        sites = ["-"]
    else:
        try:
            sites = (store or svc.store).sites()
        except Exception as e:           # noqa: BLE001 — the shops store did not answer: try again next pass
            log.write(json.dumps({"store": type(e).__name__}) + "\n")
            return {}

    def run(site):
        try:
            if svc.app:
                record = (store or svc.store).get(site)
                if not record:
                    return
                from app import user_key
                key, secret = user_key(record)
                who = {"site": site, "url": record["url"], "key": key, "secret": secret}
            else:
                who = svc.one
            out[site] = one_pass(svc, who)
        except (F.FeedError, ShopError) as e:
            out[site] = {"error": str(e)[:200]}
        except Exception as e:           # noqa: BLE001 — one shop's failure never stops the others
            out[site] = {"error": type(e).__name__}
        finally:
            log.write(json.dumps({"site": site, **out.get(site, {})}) + "\n")
            log.flush()
            if finished is not None:
                finished(site)

    started = []
    for site in sites:
        if busy.get(site) is not None and busy[site].is_alive():
            out[site] = {"busy": True}   # its last pass has not finished: never two at once for one shop
            continue
        busy[site] = threading.Thread(target=run, args=(site,), daemon=True)
        busy[site].start()
        started.append(busy[site])
    end = time.monotonic() + deadline
    for th in started:
        th.join(max(0.0, end - time.monotonic()))
    return out


def serve(svc):
    busy = {}
    while True:
        try:
            pass_all(svc, busy=busy)
        except Exception as e:           # noqa: BLE001 — the worker never dies
            print(json.dumps({"worker": type(e).__name__}), flush=True)
        time.sleep(float(svc.conf.get("PP_WATCH") or 30))
