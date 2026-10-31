#!/usr/bin/env python3
"""A price list with a photo for each item: one self-contained page that prints to PDF, and a CSV for a spreadsheet.

    BASE=https://<your-site> KEY=<api key> SECRET=<api secret> \\
      python3 catalogue.py --price-list "Wholesale" --name "A distributor" --out price_list.html --csv price_list.csv

It reads the price list's item prices and each item's picture over the shop's record API (the pictures are files kept in
the shop), and writes ONE HTML file: the pictures sit inside it as data, it loads nothing from outside and carries no
script, and it is laid out for A4, one section per item group. Open it in any browser and print it to PDF. The key needs
read on Item Price and Item (and on the files the pictures are).

  * An item with no picture, a picture kept outside the shop, a picture over --max-image-kb or one that is not a PNG, JPEG,
    GIF or WebP gets a grey "No photo" box, and is listed in the report on the last lines of the run.
  * Only general prices: a row for one customer, supplier or batch is skipped, and so is a row not valid today (the date on
    this machine, or --date). A disabled item is left out and listed.
  * A photo the shop will not give (deleted, not readable, or redirected to another host) is a grey box and listed too; the
    program never follows a redirect to another host, so the key never leaves the shop.
  * Where an item has two prices in one unit, the one with the later start date is printed.
Python 3 standard library only. It only reads: it never writes to the shop."""
from __future__ import annotations

import argparse
import base64
import csv
import datetime
import html
import http.client
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation

PAGE = 200  # rows per request
CHUNK = 40  # item codes per item request (the request line stays short)
UNGROUPED = "Other"
_SNIFF = ((b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"), (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif"))


class Unreadable(Exception):
    """A file the shop would not give (deleted, not ours to read, or moved to another host)."""


class _SameHost(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect to another host: the key goes with a redirected request, and a picture from outside the shop
    is exactly what the page promises not to hold."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
        if new.netloc != old.netloc or new.scheme != old.scheme:  # another host, or https down to http: the key must not follow
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Shop:
    """The shop's record API, read only."""

    def __init__(self, base, key, secret, timeout=60):
        self.base, self.timeout = base.rstrip("/"), timeout
        if not self.base.startswith("https://") and not self.base.startswith(("http://127.0.0.1", "http://localhost")):
            raise SystemExit("the shop's address must start with https:// (the key travels with every request)")
        self.auth = {"Authorization": f"token {key}:{secret}", "Accept": "application/json"}
        self.opener = urllib.request.build_opener(_SameHost)

    def _open(self, url):
        return self.opener.open(urllib.request.Request(url, headers=self.auth), timeout=self.timeout)

    def _read(self, url):
        try:
            return self._open(url)
        except urllib.error.HTTPError as e:
            raise SystemExit(f"the shop answered HTTP {e.code} to {url.split('?')[0]}: {e.read()[:200].decode('utf8', 'replace')}")

    def list(self, doctype, fields, filters, start):
        q = {"fields": json.dumps(fields), "filters": json.dumps(filters), "limit_start": str(start),
             "limit_page_length": str(PAGE), "order_by": "name asc"}  # text as text: a quoted order_by is ignored
        with self._read(f"{self.base}/api/resource/{urllib.parse.quote(doctype)}?{urllib.parse.urlencode(q)}") as r:
            return json.load(r)["data"]

    def file(self, path, limit):
        """The bytes of a file kept in the shop, or None when it is larger than ``limit`` bytes."""
        try:
            with self._open(self.base + urllib.parse.quote(path, safe="/%:@")) as r:
                data = r.read(limit + 1)
        except urllib.error.HTTPError as e:
            e.close()
            raise Unreadable(f"the shop answered HTTP {e.code}")
        except (urllib.error.URLError, http.client.HTTPException) as e:
            raise Unreadable(f"the shop could not be reached ({getattr(e, 'reason', type(e).__name__)})")
        return None if len(data) > limit else data


def _all(shop, doctype, fields, filters):
    start, out = 0, []
    while True:
        got = shop.list(doctype, fields, filters, start)
        out += got
        if len(got) < PAGE:
            return out
        start += PAGE


def _day(v):
    return str(v)[:10] if v else None


def read_prices(shop, price_list, today):
    """The list's general prices valid today, one per item and unit (the later start date wins)."""
    rows = _all(shop, "Item Price", ["item_code", "item_name", "uom", "price_list_rate", "currency", "customer", "supplier",
                                     "batch_no", "valid_from", "valid_upto"], [["price_list", "=", price_list]])
    best = {}
    for r in rows:
        if r.get("customer") or r.get("supplier") or r.get("batch_no"):
            continue
        if (_day(r.get("valid_from")) or "") > today or (_day(r.get("valid_upto")) or "9999") < today:
            continue
        k = (r["item_code"], r.get("uom") or "")
        if k not in best or (_day(r.get("valid_from")) or "") > (_day(best[k].get("valid_from")) or ""):
            best[k] = r
    return sorted(best.values(), key=lambda r: (r["item_code"], r.get("uom") or ""))


def read_items(shop, codes):
    out = {}
    for i in range(0, len(codes), CHUNK):
        for it in _all(shop, "Item", ["name", "item_name", "item_group", "image", "stock_uom", "disabled"],
                       [["name", "in", codes[i:i + CHUNK]]]):
            out[it["name"]] = it
    return out


def picture(shop, path, max_kb):
    """(data address, None) for a picture kept in the shop, else (None, the reason)."""
    if not path:
        return None, "no picture on the item"
    if not path.startswith("/") or path.startswith("//"):
        return None, "the picture is kept outside the shop"
    try:
        data = shop.file(path, max_kb * 1024)
    except Unreadable as e:
        return None, f"the picture could not be read: {e}"
    if data is None:
        return None, f"the picture is over {max_kb} kB"
    kind = next((m for sig, m in _SNIFF if data.startswith(sig)), None)
    if kind is None and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        kind = "image/webp"
    if kind is None:
        return None, "the picture is not a PNG, JPEG, GIF or WebP"
    return f"data:{kind};base64,{base64.b64encode(data).decode()}", None


def money(v, sep=","):
    """A rate as printed: two decimals when it has no more, else all of its decimals; ``sep`` groups the thousands."""
    try:
        d = Decimal(str(v)).quantize(Decimal(1).scaleb(-9))  # the shop stores nine decimals; a float's noise past them is dropped
    except InvalidOperation:
        return str(v)
    return f"{d:{sep}.2f}" if d == d.quantize(Decimal("0.01")) else f"{d.normalize():{sep}f}"


def build(shop, price_list, today, max_kb=800):
    """The catalogue: {"rows": [...], "report": {...}}; each row has its group, code, name, unit, rate, currency, picture."""
    prices = read_prices(shop, price_list, today)
    items = read_items(shop, sorted({p["item_code"] for p in prices}))
    cache, rows, missing, disabled, unreadable = {}, [], [], [], []
    for p in prices:
        it = items.get(p["item_code"])
        if it is None:  # a price whose item the key cannot read (or that was deleted): not offered, and said
            unreadable.append(p["item_code"])
            continue
        if it.get("disabled"):
            disabled.append(p["item_code"])  # a discontinued item keeps its price row; it is not offered
            continue
        path = it.get("image")
        if path not in cache:
            cache[path] = picture(shop, path, max_kb)
        pic, why = cache[path]
        if pic is None:
            missing.append({"item": p["item_code"], "why": why})
        rows.append({"group": it.get("item_group") or UNGROUPED, "code": p["item_code"],
                     "name": it.get("item_name") or p.get("item_name") or p["item_code"], "uom": p.get("uom") or it.get("stock_uom") or "",
                     "rate": money(p["price_list_rate"]), "plain": money(p["price_list_rate"], sep=""), "currency": p.get("currency") or "", "picture": pic})
    rows.sort(key=lambda r: (r["group"] == UNGROUPED, r["group"], r["name"], r["code"]))
    return {"rows": rows, "report": {"prices": len(prices), "with_picture": sum(1 for r in rows if r["picture"]),
                                     "without_picture": missing, "disabled": disabled,
                                     "item_not_readable": unreadable}}


CSS = """@page{size:A4;margin:12mm}body{font-family:Arial,sans-serif;color:#222;margin:0}
h1{font-size:20px;margin:0}h2{font-size:15px;margin:14px 0 6px;border-bottom:2px solid #1F3864;color:#1F3864;break-after:avoid}
.meta{color:#555;font-size:12px;margin:2px 0 8px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.card{border:1px solid #ccc;padding:6px;break-inside:avoid;font-size:12px}.card .ph{height:34mm;display:flex;align-items:center;justify-content:center;background:#f2f2f2;color:#888}
.card img{max-width:100%;max-height:34mm;object-fit:contain}.card .n{font-weight:bold;margin-top:4px}.card .c{color:#666;font-size:11px}
.card .p{font-size:14px;margin-top:2px}"""


def render_html(rows, distributor, list_name, today):
    e = html.escape
    out = [f"<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><title>{e(distributor)} — {e(list_name)}</title>"
           f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><style>{CSS}</style></head><body>"
           f"<h1>{e(distributor)}</h1><div class=\"meta\">{e(list_name)} · {e(today)}</div>"]
    group = None
    for r in rows:
        if r["group"] != group:
            out.append(("</div>" if group is not None else "") + f"<h2>{e(r['group'])}</h2><div class=\"grid\">")
            group = r["group"]
        pic = f"<img src=\"{r['picture']}\" alt=\"{e(r['name'])}\">" if r["picture"] else "No photo"
        out.append(f"<div class=\"card\"><div class=\"ph\">{pic}</div><div class=\"n\">{e(r['name'])}</div>"
                   f"<div class=\"c\">{e(r['code'])}{' · ' + e(r['uom']) if r['uom'] else ''}</div>"
                   f"<div class=\"p\">{e(r['currency'])} {e(r['rate'])}</div></div>")
    out.append("</div></body></html>\n" if group is not None else "<p>No prices on this list.</p></body></html>\n")
    return "".join(out)


def _cell(v):
    """A spreadsheet runs a cell that starts with = + - @ as a formula: put a quote in front, as the shop's own exports do."""
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def render_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["Group", "Item code", "Item name", "Unit", "Currency", "Rate", "Photo"])
    for r in rows:
        w.writerow([_cell(r["group"]), _cell(r["code"]), _cell(r["name"]), _cell(r["uom"]), _cell(r["currency"]), r["plain"],
                    "yes" if r["picture"] else "no"])
    return buf.getvalue()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", default=os.environ.get("BASE"), help="the shop's address (or BASE)")
    ap.add_argument("--key", default=os.environ.get("KEY"))
    ap.add_argument("--secret", default=os.environ.get("SECRET"))
    ap.add_argument("--price-list", required=True)
    ap.add_argument("--name", required=True, help="the name printed at the top of the page: the distributor who sends the list")
    ap.add_argument("--list-title", help="the list's printed name (default: the price list's name)")
    ap.add_argument("--out", default="price_list.html")
    ap.add_argument("--csv", help="also write a spreadsheet-ready CSV here")
    ap.add_argument("--max-image-kb", type=int, default=800)
    ap.add_argument("--date", default=None, help="the day prices must be valid on, YYYY-MM-DD (default: today on this machine)")
    a = ap.parse_args(argv)
    if not (a.base and a.key and a.secret):
        ap.error("give --base, --key and --secret (or BASE, KEY and SECRET)")
    today = a.date or datetime.date.today().isoformat()
    cat = build(Shop(a.base, a.key, a.secret), a.price_list, today, a.max_image_kb)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(render_html(cat["rows"], a.name, a.list_title or a.price_list, today))
    if a.csv:
        with open(a.csv, "w", encoding="utf-8-sig", newline="") as f:
            f.write(render_csv(cat["rows"]))
    rep = cat["report"]
    print(f"{a.out}: {rep['prices']} price(s), {rep['with_picture']} with a picture, {len(rep['without_picture'])} without")
    if rep["item_not_readable"]:
        print(f"  left out, item not readable by this key: {', '.join(sorted(set(rep['item_not_readable'])))}")
    if rep["disabled"]:
        print(f"  left out, disabled item(s): {', '.join(sorted(set(rep['disabled'])))}")
    for m in rep["without_picture"]:
        print(f"  no photo: {m['item']} — {m['why']}")
    if not cat["rows"]:
        print("  nothing to print: no general price valid on that day on this list (check the list's name, and --date)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
