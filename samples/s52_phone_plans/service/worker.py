"""S52 — after payment: the event feed tells the service a sale was paid; it activates each plan on it with the telecom
company and writes the number to the retailer's own records. Each pass also keeps the plans' prices in step.

Per retailer, each pass (the container: every PP_WATCH seconds, default 30; CitiXsys hosting: each scheduled call):
  1. the retailer's feed (the kit's ``tools/feed_client``), with that retailer's app user key and its own
     handled-events note (``PP_STATE/<site's hash>/``): a paid sale (``sale.booked``) with plan lines is activated;
  2. the plans' prices: the telecom company's price for THIS retailer's account, written to the retailer's price list
     (``Item Price``) where it differs, so the till sells the plan at that price.

ACTIVATION, ONCE. Each plan line has its own key, ``<sale>:<line>``. Its ``PP TEL Activation`` row is NAMED by that key
(the retailer's iVendNext refuses a second), and the same key goes to the telecom company as the call's Idempotency-Key,
so a call whose answer was lost, asked again on the next pass, gets the same number and never a second activation.
  * the telecom company answers late or not at all: the row stays *Pending* and the event stays undone; the next pass
    asks again with the same key;
  * the telecom company refuses: the row says *Failed* with its sentence, and nobody retries (the store sorts it out
    with the customer, see the README);
  * activated: the row says *Activated* with the number. It is listed under the sale's Connections.
"""

from __future__ import annotations

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
import plans  # noqa: E402
import telecom  # noqa: E402
from shop import Duplicate, ShopError  # noqa: E402

PASS_DEADLINE_S = 25


def activate_sale(svc, t, s: dict, sale: str, site: str = "-") -> list[dict]:
    """Activate every plan line of one paid sale; returns what happened to each. The telecom company's idempotency key is
    the retailer's site and the sale line, so two retailers' sales of the same name are never one activation, whatever
    way a real telecom company scopes its keys."""
    inv = t.get("POS Invoice", sale)
    if not inv:
        return []
    tel = svc.telecom(s, timeout=float(svc.conf.get("TEL_ACTIVATE_TIMEOUT") or 10))
    work = plans.activation_work(inv, s, tel.plans() if any(
        s["plan_group"] and ln.get("item_group") == s["plan_group"] for ln in inv.get("items") or []) else [])
    act, done = f"{svc.prefix} Activation", []
    for w in work:
        row = t.get(act, w["key"])
        if row and row.get("status") in ("Activated", "Failed"):
            done.append({"key": w["key"], "status": row["status"], "again": True})
            continue
        if not row:
            try:
                t.insert({"doctype": act, "activation_key": w["key"], "sale": w["sale"], "plan": w["plan"],
                          "phone": w["phone"] or None, "serial_no": w["serial_no"], "customer": w["customer"] or None,
                          "status": "Pending"})
            except Duplicate:
                pass                     # another pass made it a moment ago: carry on with the same key
        if not w["phone"]:
            t.update(act, w["key"], {"status": "Failed", "message": "No phone on the sale fits this plan."})
            done.append({"key": w["key"], "status": "Failed"})
            continue
        try:
            out = tel.activate(w["plan"], w["phone"], w["serial_no"], w["customer"], w["sale"], idem=f"{site}/{w['key']}")
        except telecom.TelecomRefused as e:
            t.update(act, w["key"], {"status": "Failed", "message": plans.plain(str(e))})
            done.append({"key": w["key"], "status": "Failed"})
            continue
        # TelecomDown is not caught: the row stays Pending, the event stays undone, the next pass asks again
        t.update(act, w["key"], {"status": "Activated", "activation_number": str(out.get("activation") or "")[:60],
                                 "message": ""})
        done.append({"key": w["key"], "status": "Activated"})
    return done


def sync_prices(svc, t, s: dict) -> dict:
    """The plans' prices on the retailer's price list, from the telecom company's catalogue for this account."""
    if not s["price_list"]:
        return {"skipped": "no price list in the settings"}
    catalogue = svc.telecom(s, timeout=10).plans()
    ours = {r["name"] for r in t.list("Item", [["item_group", "=", s["plan_group"]]], ["name"])} if s["plan_group"] else set()
    catalogue = [p for p in catalogue if p["code"] in ours]   # only the retailer's plan items: never another price on its list
    codes = [p["code"] for p in catalogue]
    rows = t.list("Item Price", [["price_list", "=", s["price_list"]], ["item_code", "in", codes]],
                  ["name", "item_code", "price_list_rate"]) if codes else []
    current = {r["item_code"]: r for r in rows}
    wrote, refused = 0, 0
    for ch in plans.price_changes(catalogue, current):
        try:
            if ch["name"]:
                t.update("Item Price", ch["name"], {"price_list_rate": float(ch["rate"])})
            else:
                t.insert({"doctype": "Item Price", "item_code": ch["item_code"], "price_list": s["price_list"],
                          "price_list_rate": float(ch["rate"])})
            wrote += 1
        except ShopError:                # an item the retailer has not made yet: counted, never named in the log
            refused += 1
    return {"prices_written": wrote, "prices_refused": refused}


def handler(svc, t, site: str = "-"):
    def handle(ev: dict, _db):
        if ev.get("doc_type") == "POS Invoice" and ev.get("event") == "sale.booked":
            return activate_sale(svc, t, svc.settings(t), ev["doc_name"], site)
        return None                      # every other event: marked done unread
    return handle


def state_dir(svc, site: str) -> str:
    root = svc.conf.get("PP_STATE") or os.path.join(HERE, "state")
    path = os.path.join(root, hashlib.sha256(site.encode()).hexdigest()[:16])
    os.makedirs(path, exist_ok=True)
    return path


def one_pass(svc, who: dict) -> dict:
    """One retailer: its feed, then its prices."""
    t = svc.shop(who, timeout=20)
    feed = F.DoorFeed(F.Api(who["url"], who["key"], who["secret"]))
    seen = F.Store(os.path.join(state_dir(svc, who["site"]), "feed.sqlite"))
    site = who["site"] if who["site"] != "-" else who["url"].split("://", 1)[-1]     # one retailer: its address's host
    out = {"feed": F.poll(feed, seen, handler(svc, t, site))}
    out.update(sync_prices(svc, t, svc.settings(t)))
    return out


def pass_all(svc, store=None, log=sys.stdout, deadline: float = PASS_DEADLINE_S, finished=None, busy: dict | None = None) -> dict:
    """One pass over every connected retailer, each on its own thread, so a slow retailer never holds up another."""
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
        except Exception as e:           # noqa: BLE001 — one retailer's failure never stops the others
            out[site] = {"error": type(e).__name__}
        finally:
            log.write(json.dumps({"site": site, **{k: (v if k == "error" else "done") for k, v in out.get(site, {}).items()}}) + "\n")
            log.flush()
            if finished is not None:
                finished(site)

    started = []
    for site in sites:
        if busy.get(site) is not None and busy[site].is_alive():
            out[site] = {"busy": True}   # its last pass has not finished: never two at once for one retailer
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
