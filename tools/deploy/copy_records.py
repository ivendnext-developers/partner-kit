#!/usr/bin/env python3
"""copy_records — move a shop's records from one installed app to another: from our app to your own version of it.

A customer that runs one of our App library apps and moves to your version of it (``tools/manifest/rename.py``,
recipe *Make one of our apps your own*) keeps its records. Install your version beside ours first: the two prefixes never
share a name. Then copy, check, and only then uninstall ours (its uninstall also exports every record to a file).

    BASE=https://<the customer's site> KEY=<api key> SECRET=<api secret> \\
        python3 tools/deploy/copy_records.py ivendnext_bln acme_bins            # shows what it would copy
    ... python3 tools/deploy/copy_records.py ivendnext_bln acme_bins --write    # copies, then counts both sides

What it reads, from the site's own record of each install (``Retail Extension Install``): the record types each app made
and the fields each added to the shop's own records. Each record type of the first app is matched to the one of yours
with the same name after the prefix (``IVENDNEXT BLN Bin`` → ``ACME BINS Bin``), and each field the same way
(``ivendnext_bln_default_bin`` → ``acme_bins_default_bin``).

What it writes:
- every record of each record type, in the order its links need (a location before its aisles, an aisle before its
  bins), with the fields your record type has, and the rows of its tables;
- a link to another of the app's own records points at that record's copy;
- each value the first app's fields hold on the shop's own records (an item's default bin) into your field.

A record whose name comes from its own fields (a bin named by its code) keeps its name, and one your app already holds
under that name is left as it is, so a second run copies only what is new. A record the site names itself (a number or
a random name) is copied only into a record type of yours that is still empty: a second run refuses it, because its copy
cannot be told apart from a record made in your app. A value your app already holds on the shop's own records is never
overwritten. A submitted record is copied submitted, in one step. A field the first app has and yours does not is listed,
never guessed. A cancelled record is not copied. It deletes nothing, on either side. The key is a System Manager's (it
reads both installs' records and writes yours).

Exit codes: 0 every record is on both sides (or, without --write, nothing stops the copy) · 1 refused or a count
differs · 2 usage.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

INSTALL = "Retail Extension Install"
PAGE = 500
SKIP_TYPES = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading", "Fold", "Image"}
SYSTEM = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "doctype", "parent",
          "parentfield", "parenttype", "_user_tags", "_comments", "_assign", "_liked_by", "_seen", "amended_from"}


class Refused(Exception):
    pass


class Site:
    """The four calls the copy makes, through the site's record API."""

    def __init__(self, base, key, secret):
        self.base, self.auth = base.rstrip("/"), f"token {key}:{secret}"

    def _req(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Authorization": self.auth, "Accept": "application/json",
                                              **({"Content-Type": "application/json"} if data is not None else {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"null") or {}
        except urllib.error.HTTPError as e:
            if e.code == 404 and method == "GET":
                return None
            raise Refused(f"the site answered HTTP {e.code} to {method} {urllib.parse.unquote(path.split('?')[0])}: {_why(e.read())}")
        except (urllib.error.URLError, http.client.HTTPException) as e:
            raise Refused(f"the site did not answer: {getattr(e, 'reason', type(e).__name__)}")

    def get(self, doctype, name):
        got = self._req("GET", f"/api/resource/{urllib.parse.quote(doctype)}/{urllib.parse.quote(name, safe='')}")
        return (got or {}).get("data") if got else None

    def names(self, doctype, filters=None, fields=("name",)):
        out, start = [], 0
        while True:
            qs = urllib.parse.urlencode({"fields": json.dumps(list(fields)), "filters": json.dumps(filters or []),
                                         "limit_start": start, "limit_page_length": PAGE, "order_by": "creation asc"})
            page = (self._req("GET", f"/api/resource/{urllib.parse.quote(doctype)}?{qs}") or {}).get("data") or []
            out += page
            if len(page) < PAGE:
                return out
            start += PAGE

    def insert(self, doctype, doc):
        return (self._req("POST", f"/api/resource/{urllib.parse.quote(doctype)}", doc) or {}).get("data") or {}

    def update(self, doctype, name, values):
        self._req("PUT", f"/api/resource/{urllib.parse.quote(doctype)}/{urllib.parse.quote(name, safe='')}", values)


def _why(raw):
    try:
        b = json.loads(raw or b"{}")
        msgs = [json.loads(m).get("message", m) for m in json.loads(b.get("_server_messages") or "[]")]
        return "; ".join(msgs) or b.get("exc_type") or "no reason given"
    except (ValueError, AttributeError, TypeError):
        return "no reason given"


def installed(site, app):
    """(prefix, [own record types, not tables], {(shop record type, field)}) of an installed app."""
    rec = site.get(INSTALL, app)
    if not rec or str(rec.get("status") or "").lower() != "installed":
        raise Refused(f"{app} is not installed on this site" + (f" (its install reads {rec.get('status')})" if rec else ""))
    items = json.loads(rec.get("items") or "[]")
    types = [it["name"] for it in items if it.get("kind") == "doctype" and not it.get("istable")]
    fields = {(it["dt"], it["fieldname"]) for it in items if it.get("kind") == "custom_field" and it.get("dt")}
    if not rec.get("prefix"):
        raise Refused(f"{app}: its install record names no prefix")
    return rec["prefix"], types, fields


def meta(site, doctype):
    """{fieldname: field} of a record type (no layout fields); the record type's own naming under the key ``None``."""
    d = site.get("DocType", doctype)
    if not d:
        raise Refused(f"cannot read the record type {doctype} (the key needs System Manager)")
    out = {f["fieldname"]: f for f in d.get("fields") or [] if f.get("fieldtype") not in SKIP_TYPES and f.get("fieldname")}
    out[None] = {"autoname": d.get("autoname") or ""}
    return out


def named_by_fields(m) -> bool:
    """A record type whose records are named from their own fields: its copy takes the same name."""
    a = (m.get(None) or {}).get("autoname", "").strip().lower()
    return a.startswith("field:") or (a.startswith("format:") and "#" not in a) or a == "prompt"


def order(types, metas):
    """The record types in the order their links need: each after every own type it links to."""
    deps = {t: {f.get("options") for k, f in metas[t].items() if k and f.get("fieldtype") == "Link"
                and f.get("options") in types and f.get("options") != t} for t in types}
    done, out = set(), []
    while len(out) < len(types):
        ready = [t for t in types if t not in done and deps[t] <= done]
        if not ready:
            raise Refused("these record types link to each other in a circle: " + ", ".join(sorted(set(types) - done)))
        for t in ready:
            done.add(t)
            out.append(t)
    return out


def plan(site, src_app, dst_app):
    sp, stypes, sfields = installed(site, src_app)
    dp, dtypes, dfields = installed(site, dst_app)
    pairs, missing = {}, []
    for t in stypes:
        twin = dp + t[len(sp):] if t.startswith(sp + " ") else None
        (pairs.__setitem__(t, twin) if twin in dtypes else missing.append(t))
    if missing:
        raise Refused("no record type of " + dst_app + " matches " + ", ".join(missing) +
                      f" (each {sp} <name> needs a {dp} <name>)")
    sfp, dfp = src_app + "_", dst_app + "_"
    fpairs = {}
    for dt, fn in sorted(sfields):
        twin = (dt, dfp + fn[len(sfp):]) if fn.startswith(sfp) else None
        if twin in dfields:
            fpairs[(dt, fn)] = twin[1]
    return sp, dp, pairs, fpairs, sorted(set(sfields) - set(fpairs))


def copy(site, src_app, dst_app, write=False, out=print) -> int:
    sp, dp, pairs, fpairs, nofield = plan(site, src_app, dst_app)
    smeta = {t: meta(site, t) for t in pairs}
    dmeta = {pairs[t]: meta(site, pairs[t]) for t in pairs}
    back = {d: t for t, d in pairs.items()}             # your record type -> ours
    names = {t: {} for t in pairs}                       # our record type -> {our record's name: its copy's name}
    for t, d in pairs.items():                           # refused before anything is written
        if not named_by_fields(dmeta[d]) and site.names(d):
            raise Refused(f"{d} already holds records, and the site names its records itself: a copy could not be told "
                          "apart from a record made in your app. Copy into an empty one.")
    bad = 0
    for t in order(list(pairs), smeta):
        d = pairs[t]
        lost = sorted(k for k in set(smeta[t]) - set(dmeta[d]) if k)
        if lost:
            out(f"note: {d} has no field {', '.join(lost)}: those values are not copied")
        rows = site.names(t, fields=("name", "docstatus"))
        made = there = skipped = 0
        for r in rows:
            if r.get("docstatus") == 2:
                skipped += 1
                continue
            have = site.get(d, r["name"]) if named_by_fields(dmeta[d]) else None
            if have:
                names[t][r["name"]] = have["name"]
                there += 1
                continue
            if not write:
                made += 1
                continue
            src = site.get(t, r["name"]) or {}
            doc = _copy_doc(site, src, smeta[t], dmeta[d], back, names)
            if src.get("docstatus") == 1:
                doc["docstatus"] = 1                     # submitted on insert: a refusal leaves no draft behind
            got = site.insert(d, doc)
            names[t][r["name"]] = got.get("name") or r["name"]
            made += 1
        verb = "copied" if write else "to copy"
        out(f"{t} → {d}: {len(rows)} record(s); {made} {verb}, {there} already there"
            + (f", {skipped} cancelled not copied" if skipped else ""))
        if write:
            held = {x["name"] for x in site.names(d)}
            lost_rows = [n for n in (r["name"] for r in rows if r.get("docstatus") != 2) if names[t].get(n) not in held]
            if lost_rows:
                out(f"  ⚠ {d} lacks the copy of {len(lost_rows)} record(s): {', '.join(lost_rows[:5])}")
                bad += 1
    for (dt, fn), twin in fpairs.items():
        of = (meta(site, dt).get(fn) or {}).get("options")
        held = site.names(dt, filters=[[fn, "is", "set"]], fields=("name", fn, twin))
        todo = [h for h in held if not h.get(twin)]      # a value already set in your app is never overwritten
        out(f"{dt}.{fn} → {dt}.{twin}: {len(held)} value(s); {len(todo)} {'copied' if write else 'to copy'}, "
            f"{len(held) - len(todo)} already set")
        if write:
            for h in todo:
                site.update(dt, h["name"], {twin: names.get(of, {}).get(h.get(fn), h.get(fn))})
    for dt, fn in nofield:
        out(f"note: {dst_app} adds no field matching {dt}.{fn}: its values are not copied")
    if not write:
        out("nothing written (add --write)")
    return 1 if bad else 0


def _copy_doc(site, src, smeta, dmeta, back, names):
    """The record as your record type takes it: its fields and table rows, each link to one of the app's own records
    pointed at that record's copy (looked up in the names of the record type the link names, never another's)."""
    def value(f, v):
        if f.get("fieldtype") == "Link" and f.get("options") in back and isinstance(v, str):
            return names[back[f["options"]]].get(v, v)
        return v

    doc = {"name": src.get("name")}          # kept where the record type takes a given name; else the site names it
    for fn, f in dmeta.items():
        if not fn or fn not in smeta or fn in SYSTEM or fn not in src:
            continue
        v = src[fn]
        if f.get("fieldtype") in ("Table", "Table MultiSelect"):
            child = meta(site, f["options"])
            doc[fn] = [{k: value(child.get(k, {}), row[k]) for k in row if k in child and k and k not in SYSTEM}
                       for row in (v or [])]
        else:
            doc[fn] = value(f, v)
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Copy a shop's records from one installed app to another (ours to yours).")
    ap.add_argument("from_app", help="the app whose records are copied, e.g. ivendnext_bln")
    ap.add_argument("to_app", help="your app, installed beside it, e.g. acme_bins")
    ap.add_argument("--write", action="store_true", help="copy (otherwise only show what would be copied)")
    a = ap.parse_args(argv)
    base, key, secret = os.environ.get("BASE"), os.environ.get("KEY"), os.environ.get("SECRET")
    if not (base and key and secret):
        print("set BASE (https://<site>), KEY and SECRET (a System Manager's API key) in the environment")
        return 2
    try:
        return copy(Site(base, key, secret), a.from_app, a.to_app, a.write)
    except Refused as e:
        print(f"REFUSED: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
