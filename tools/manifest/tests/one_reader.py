#!/usr/bin/env python3
"""Run the one reader of an app made from S22 and S25 (its service's ``feed`` schedule) with each part's real code, in a
process of its own, and print what each run did as one JSON line. test_combine.py's OneReader reads it.

    python3 one_reader.py <app folder> <state folder> handed        one sale and one new customer, two runs
    python3 one_reader.py <app folder> <state folder> fails-once    the same, S25's part failing on the sale in run 1
    python3 one_reader.py <app folder> <state folder> new-copy      fails-once, run 2 in a new copy of the function: its
                                                                    working folder (each part's seen-list) starts empty
    python3 one_reader.py <app folder> <state folder> unreachable   each part opens the shop itself (nothing patched)

Only the shop is a stand-in: each part is given its own sample's fake shop (from the app's ``tests/<tag>/``) through its
own ``worker.open_shop``, and both share one fake feed, which counts its reads and records what is marked done and
each failure's note. Each part's handler, seen-list and scheduled pass are its own, as the app runs them.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys

SITE = "shop-a.example"


class Feed:
    """One shop's feed: the not-done events, oldest first; ``reads`` counts each call of ``events``."""

    def __init__(self, events):
        self.q, self.reads, self.marked, self.notes = list(events), 0, [], {}

    def events(self, limit=100, page=None):
        self.reads += 1
        left = [e for e in self.q if e["id"] not in self.marked]
        return left[:limit], None, len(left)

    def done(self, ids):
        self.marked += [i for i in ids if i not in self.marked]
        return len(ids)

    def failed(self, id_, note):
        self.notes.setdefault(id_, []).append(note)

    def backlog(self):
        return len([e for e in self.q if e["id"] not in self.marked])


def load(app_dir: str, tag: str):
    """The part's sample's fake shop, with the part's own shop.py (``service/<tag>/service/``) as the one it imports."""
    sys.modules.pop("shop", None)
    sys.path.insert(0, os.path.join(app_dir, "service", tag, "service"))
    try:
        spec = importlib.util.spec_from_file_location(f"fake_shop_{tag}", os.path.join(app_dir, "tests", tag, "fake_shop.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
        sys.modules.pop("shop", None)
    return module


def main(app_dir: str, state: str, scenario: str) -> dict:
    url = "http://127.0.0.1:9" if scenario == "unreachable" else f"https://{SITE}"
    with open(os.path.join(state, "shops.json"), "w", encoding="utf-8") as f:
        json.dump({SITE: {"site": SITE, "url": url, "secrets": {"user:acme-hk@x.example": "k:s"}}}, f)
    os.environ.update(IVN_LIBRARY_APP="acme_hk", IVN_SHOPS_FILE=os.path.join(state, "shops.json"), PP_STATE=state)
    sys.path.insert(0, os.path.join(app_dir, "service"))
    import app as service  # noqa: E402  (the app's one service)
    out = {"readers": sorted(service.READERS), "handoff": service.HUB is not None, "runs": []}
    if scenario == "unreachable":
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            service.lambda_handler({"ivn_schedule": "feed"})
        out["log"] = [json.loads(line) for line in log.getvalue().splitlines() if line.startswith("{")]
        return out
    for tag in service.READERS:
        service._load(tag)
    own = {tag: service._parts[tag][1] for tag in service.READERS}
    lyl, gcs = load(app_dir, "lyl"), load(app_dir, "gcs")
    t_lyl, t_gcs = lyl.shop(), gcs.shop()
    lyl.sale(t_lyl, "S1", "C1", "400.00")
    gcs.sale(t_gcs, "S1")
    t_lyl.put("Customer", "C2", customer_group="Individual")
    feed = Feed([{"id": "e1", "event": "sale.booked", "doc_type": "POS Invoice", "doc_name": "S1", "raw_event": "on_submit",
                  "at": "2026-10-31 09:00:00"},
                 {"id": "e2", "event": "customer.created", "doc_type": "Customer", "doc_name": "C2",
                  "raw_event": "after_insert", "at": "2026-10-31 09:00:01"}])
    own["lyl"]["worker"].open_shop = lambda record: (t_lyl, feed)
    own["gcs"]["worker"].open_shop = lambda record: (t_gcs, feed)
    calls = {"lyl": 0, "gcs": 0}
    real_sale, real_earn = own["gcs"]["cards"].on_sale, own["lyl"]["loyalty"].on_sale

    def gcs_sale(*a, **k):
        calls["gcs"] += 1
        if scenario in ("fails-once", "new-copy") and calls["gcs"] == 1:
            raise RuntimeError("the gift card service did not answer")
        return real_sale(*a, **k)

    def lyl_earn(*a, **k):
        calls["lyl"] += 1
        return real_earn(*a, **k)

    own["gcs"]["cards"].on_sale, own["lyl"]["loyalty"].on_sale = gcs_sale, lyl_earn
    ledger = f"{service.MOUNTS['lyl']['prefix']} Ledger"
    member = f"{service.MOUNTS['lyl']['prefix']} Member"
    card = f"{service.MOUNTS['gcs']['prefix']} Card"
    for run in range(2):
        if run == 1 and scenario == "new-copy":       # the working folder is gone; the shops store (the table) is not
            for d in os.listdir(state):
                if os.path.isdir(os.path.join(state, d)):
                    shutil.rmtree(os.path.join(state, d))
        reads = feed.reads
        with contextlib.redirect_stdout(io.StringIO()):
            result = service.lambda_handler({"ivn_schedule": "feed"})
        out["runs"].append({
            "reads": feed.reads - reads, "marked": list(feed.marked), "notes": {k: list(v) for k, v in feed.notes.items()},
            "earned": sorted(r["source_key"] for r in t_lyl.db.get(ledger, {}).values() if r.get("entry_type") == "Earn"),
            "members": sorted(t_lyl.db.get(member, {})), "cards": sorted(t_gcs.db.get(card, {})),
            "gift_card_calls": calls["gcs"], "loyalty_calls": calls["lyl"], "feed": result.get("feed"),
            "waiting_record": [(r or {}).get("events", {}) for n, r in json.load(open(os.path.join(state, "shops.json"),
                                     encoding="utf-8")).items() if n.startswith("handoff|")]})
    return out


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:4]), default=str))
