"""S3 outside — the price-deviation service. Runs on the partner's own server, never in the shop (the four rules: your code runs on your server).

For every booked sale the event feed announces (``sale.booked``, ``return.booked`` and ``invoice.booked`` for a
back-office sale that is not the day's till roll-up), it reads the sale over the record API with the service's own key,
and writes one ``PP PDO Deviation`` record (installed by this sample's manifest) per SOLD line (a positive quantity)
charged below list by more than the threshold. So a return is judged only for the items it sells (an exchange), and an
item handed back inside a sale is never judged. The record's name is the sale line's id, so a second delivery of the
same event writes nothing.

The threshold is the shop's own: its ``PP PDO Settings`` record ``Default``, read with the same key at the first sale of
each pass, so a change applies on the next pass. A shop with no such record yet is judged at PP_THRESHOLD (10 unless
set). A shop that refuses the read fails the event, which stays not done and is tried again: never a silent default.
The threshold read at a pass's first sale holds for that whole pass, so a change applies to the sales checked after it.

    IVN_BASE=… FEED_KEY=… FEED_SECRET=… [PP_THRESHOLD=10] python3 service.py [--door-prefix pp_feed.api] [--watch 30]
One shop. For many shops, each connecting itself (the App library's app on CitiXsys hosting), run ``app.py``.
Standard library only, plus the event-feed client (tools/feed_client/feed_client.py — copy that one file).
"""
import argparse
import json
import os
import pathlib
import sys
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2] / "tools" / "feed_client")]
import feed_client as F  # noqa: E402
from core import deviations  # noqa: E402

DT, SETTINGS = "PP PDO Deviation", "PP PDO Settings"     # use_prefix() renames both for the library's app
DEFAULT_THRESHOLD = 10.0


def use_prefix(prefix: str):
    """The record types under another prefix: ``IVENDNEXT PDA`` for the App library's app."""
    global DT, SETTINGS
    DT, SETTINGS = f"{prefix} Deviation", f"{prefix} Settings"


def threshold_of(api, fallback=DEFAULT_THRESHOLD) -> float:
    """The shop's own threshold, from its Settings record ``Default``. No record yet (a 404 naming ``Default``, the
    record's name, which no translation of the shop's "not found" sentence changes):
    ``fallback``. Any other refusal (the key lacks the read right, the record type is missing, the shop does not answer)
    raises, so the event stays not done."""
    try:
        doc = api.call("GET", f"/api/resource/{urllib.parse.quote(SETTINGS)}/Default")
    except F.FeedError as e:
        if str(e).startswith("404") and "Default" in str(e):
            return float(fallback)
        raise
    value = (doc.get("data") or {}).get("threshold_percent")
    return float(fallback) if value in (None, "") else float(value)


def handler_for(api, threshold, trace=None):
    """``threshold``: a number, or a callable read once, at the first sale this handler judges (the shop's Settings)."""
    got = []

    def limit():
        if not got:
            got.append(float(threshold() if callable(threshold) else threshold))
        return got[0]

    def note(ev, what):
        if trace:
            print(json.dumps({"event": ev["event"], "doc": ev["doc_name"], "what": what}), file=trace, flush=True)

    def handle(ev, db):
        if ev["event"] not in ("sale.booked", "return.booked", "invoice.booked"):
            note(ev, "not a sale")
            return                                          # not a sale: nothing to judge (the event is still done)
        try:
            doc = api.call("GET", f"/api/resource/{urllib.parse.quote(ev['doc_type'])}/{urllib.parse.quote(ev['doc_name'])}")
        except F.FeedError as e:
            if str(e).startswith("404") and ev["doc_name"] in str(e):
                note(ev, "gone: the sale was deleted before it was read")
                return                                      # nothing left to judge; never block the feed on it
            raise
        sale = doc.get("data") or {}
        if sale.get("is_consolidated") or sale.get("docstatus") != 1:
            note(ev, f"skipped: roll-up {sale.get('is_consolidated')}, docstatus {sale.get('docstatus')}")
            return                                          # the day's roll-up of till sales already judged, or a draft
        items = sale.get("items") or []
        if any(k not in it for it in items for k in ("qty", "price_list_rate", "rate")):
            raise F.FeedError("a line's quantity or price is not readable with this key: give the role read on them")
        sold = [it for it in items if float(it["qty"] or 0) > 0]   # an exchange's sold lines too
        lines = [{"name": it["name"], "item_code": it["item_code"], "qty": it.get("qty"),
                  "price_list_rate": it["price_list_rate"], "rate": it["rate"],
                  "pricing_rules": it.get("pricing_rules") or ""} for it in sold]
        threshold = limit()
        found = deviations(lines, threshold)
        note(ev, f"{len(lines)} lines, {len(found)} below list beyond {threshold}%")
        for row in found:
            rec = {"line_key": row["name"], "invoice_doctype": ev["doc_type"], "invoice": ev["doc_name"],
                   "posting_date": sale.get("posting_date"), "pos_profile": sale.get("pos_profile"),
                   "item_code": row["item_code"], "qty": row["qty"], "price_list_rate": row["price_list_rate"],
                   "charged_rate": row["rate"], "deviation_percent": row["deviation_percent"],
                   "threshold_percent": threshold, "pricing_rules": row["pricing_rules"]}
            try:
                api.call("POST", f"/api/resource/{urllib.parse.quote(DT)}", body=rec)
                note(ev, f"recorded {row['name']}")
            except F.FeedError as e:
                if not str(e).startswith("409"):            # 409: this line was recorded by an earlier delivery
                    raise
                note(ev, f"already recorded {row['name']}")
    return handle


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--door-prefix", default="ivendnext_mpos.api.feed")
    p.add_argument("--state", default=str(HERE / "state" / "pdo.sqlite"))
    p.add_argument("--watch", type=float)
    p.add_argument("--trace", action="store_true", help="one line per event on stderr: what the service did")
    a = p.parse_args(argv)
    api = F.Api(os.environ["IVN_BASE"], os.environ["FEED_KEY"], os.environ["FEED_SECRET"])
    if os.environ.get("PDO_PREFIX"):
        use_prefix(os.environ["PDO_PREFIX"].strip())
    fallback = float(os.environ.get("PP_THRESHOLD", DEFAULT_THRESHOLD))
    feed, store = F.DoorFeed(api, a.door_prefix), F.Store(a.state)
    while True:
        handle = handler_for(api, lambda: threshold_of(api, fallback), sys.stderr if a.trace else None)
        print(json.dumps(F.poll(feed, store, handle)), flush=True)
        if not a.watch:
            break
        import time
        time.sleep(a.watch)


if __name__ == "__main__":
    main()
