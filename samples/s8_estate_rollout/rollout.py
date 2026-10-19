#!/usr/bin/env python3
"""S8 — set up an estate of regions and stores from ONE file, and keep it that way. Standard library only.

    PP_BASE=https://shop.example PP_KEY=<api key> PP_SECRET=<api secret> python3 rollout.py plan   --estate estate.json
                                                                                        … apply  --estate estate.json
                                                                                        … verify --estate estate.json
                                                                                        … remove --estate estate.json

  plan    reads the shop and says what apply WOULD change, object by object and field by field. Writes nothing.
  apply   makes the shop match the file. IDEMPOTENT: run it again and nothing is created or updated; change one price in the
          file and only that Item Price moves.
  verify  reads everything back from the shop and compares it with the file; exit 1 and every difference by name if a store
          was edited by hand behind the script's back, or something with the estate's prefix is not in the file (an orphan).
  remove  takes the estate out. A record a booked sale points at cannot be deleted (the shop keeps its history): it is
          RETIRED (disabled) and the line says so.

What the file owns, per region: a price list with its Item Prices, one promotion (limited to the region's stores — the
promotion's sources are the stores' warehouses); per store: a warehouse, a till profile cloned from the reference profile (its
price list comes from its warehouse, its receipt format), a cashier and the cashier's user permissions; per region: a manager. Estate-wide: the reason
switches and the reason codes. State: ``state/before.json`` keeps the switches' earlier values so ``remove`` can put them back.

The key belongs to a user who may edit all of those (the shop's administrator, as in S5).
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(HERE, "state", "before.json")
DAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
# a clone of the reference profile drops what is the reference's own
_DROP = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "doctype"}
_DROP_CHILD = _DROP | {"parent", "parentfield", "parenttype"}


class Shop:
    def __init__(self, base, key, secret):
        self.base, self.auth = base.rstrip("/"), f"token {key}:{secret}"

    def call(self, method, path, body=None, params=None):
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None, method=method,
                                     headers={"Authorization": self.auth, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method} {path} → {e.code}: {e.read()[:300].decode(errors='replace')}") from None

    @staticmethod
    def q(dt):
        return "/api/resource/" + urllib.parse.quote(dt)

    def get(self, dt, name):
        try:
            return self.call("GET", f"{self.q(dt)}/{urllib.parse.quote(name)}").get("data")
        except RuntimeError as e:
            if "→ 404" in str(e):
                return None
            raise

    def list(self, dt, filters, fields):
        return self.call("GET", self.q(dt), params={"filters": json.dumps(filters), "fields": json.dumps(fields),
                                                    "limit_page_length": 0}).get("data", [])

    def create(self, dt, doc, name=None):
        d = dict(doc, doctype=dt)
        if name:
            d["__newname"] = name
        return self.call("POST", self.q(dt), d).get("data")

    def update(self, dt, name, fields):
        return self.call("PUT", f"{self.q(dt)}/{urllib.parse.quote(name)}", fields).get("data")

    def delete(self, dt, name):
        """True if deleted, False if a booked record points at it (the caller retires it instead)."""
        try:
            self.call("DELETE", f"{self.q(dt)}/{urllib.parse.quote(name)}")
            return True
        except RuntimeError as e:
            if "LinkExists" in str(e) or "→ 417" in str(e):
                return False
            raise


def names(est):
    p, ab = est["prefix"], est["abbr"]
    return {"wh": lambda code: f"{p} {code} - {ab}", "profile": lambda code: f"{p} {code}"}


def wanted(est):
    """The whole estate as data: [(doctype, name, fields, extra)] in the order they must be written."""
    n, p = names(est), est["prefix"]
    regions = {r["code"]: r for r in est["regions"]}
    out = []
    for rs in est.get("reasons", []):
        out.append(("Reason Code Master", rs["id"], {"reason_type": rs["type"], "is_active": 1}, {}))
    for r in est["regions"]:
        out.append(("Price List", r["price_list"], {"currency": est["currency"], "selling": 1, "enabled": 1}, {}))
    for r in est["regions"]:
        for item, price in r["prices"].items():
            out.append(("Item Price", f"{r['price_list']} / {item}", {"price_list_rate": price}, {"item": item, "price_list": r["price_list"]}))
    for s in est["stores"]:
        # the engine derives a till profile's price list from its warehouse (``custom_selling_price_list``, refused when empty)
        out.append(("Warehouse", n["wh"](s["code"]), dict({"company": est["company"], "disabled": 0,
                                                           "custom_selling_price_list": regions[s["region"]]["price_list"]},
                                                          **est.get("warehouse_defaults", {})), {"code": s["code"]}))
    for s in est["stores"]:
        r = regions[s["region"]]
        out.append(("POS Profile", n["profile"](s["code"]), {"warehouse": n["wh"](s["code"]), "selling_price_list": r["price_list"],
                                                              "print_format": s["print_format"], "company": est["company"], "disabled": 0}, {"code": s["code"]}))
    for r in est["regions"]:
        stores = [s for s in est["stores"] if s["region"] == r["code"]]
        out.append(("Promotion Bonus Buys Master", r["promotion"]["id"],
                    {"active": 1, "discount_percent": r["promotion"]["discount_percent"], "discount_type": "Percent"},
                    {"description": r["promotion"]["description"], "sources": sorted(n["wh"](s["code"]) for s in stores)}))
    for s in est["stores"]:
        out.append(("User", s["cashier"], {"enabled": 1}, {"roles": sorted(est["roles"]["store"]), "first_name": f"{p} {s['code']}"}))
    for r in est["regions"]:
        out.append(("User", r["manager"], {"enabled": 1}, {"roles": sorted(est["roles"]["region"]), "first_name": f"{p} {r['name']} manager"}))
    for s in est["stores"]:
        out.append(("User Permission", f"{s['cashier']} | POS Profile | {n['profile'](s['code'])}", {}, {"user": s["cashier"], "allow": "POS Profile", "for_value": n["profile"](s["code"])}))
        out.append(("User Permission", f"{s['cashier']} | Warehouse | {n['wh'](s['code'])}", {}, {"user": s["cashier"], "allow": "Warehouse", "for_value": n["wh"](s["code"])}))
    for r in est["regions"]:
        for s in est["stores"]:
            if s["region"] == r["code"]:
                out.append(("User Permission", f"{r['manager']} | POS Profile | {n['profile'](s['code'])}", {},
                            {"user": r["manager"], "allow": "POS Profile", "for_value": n["profile"](s["code"])}))
    return out


class Reader:
    """What the shop holds now, read in a few list calls (never one call per object, except users and promotions)."""

    def __init__(self, shop, est):
        p, self.est = est["prefix"], est
        self.shop = shop
        like = f"{p}%"
        self.has = {
            "Reason Code Master": {r["name"]: r for r in shop.list("Reason Code Master", [["name", "like", like]], ["name", "reason_type", "is_active"])},
            "Price List": {r["name"]: r for r in shop.list("Price List", [["name", "like", like]], ["name", "currency", "selling", "enabled"])},
            "Warehouse": {r["name"]: r for r in shop.list("Warehouse", [["name", "like", like]],
                                                      ["name", "company", "disabled", "custom_selling_price_list", *est.get("warehouse_defaults", {})])},
            "POS Profile": {r["name"]: r for r in shop.list("POS Profile", [["name", "like", like]],
                                                           ["name", "warehouse", "selling_price_list", "print_format", "company", "disabled"])},
        }
        ips = shop.list("Item Price", [["price_list", "like", like]], ["name", "item_code", "price_list", "price_list_rate"])
        self.has["Item Price"], self.dup_prices = {}, []
        for r in ips:                       # a second row for the same item and list is not the first one's business: it is named
            key = f"{r['price_list']} / {r['item_code']}"
            (self.dup_prices.append(f"{key} (row {r['name']})") if key in self.has["Item Price"] else self.has["Item Price"].__setitem__(key, r))
        self.promos = {}
        for r in shop.list("Promotion Bonus Buys Master", [["name", "like", est.get("promotion_prefix", "PP-EST-") + "%"]], ["name"]):
            d = shop.get("Promotion Bonus Buys Master", r["name"])
            self.promos[r["name"]] = {"name": d["name"], "active": d["active"], "discount_percent": d["discount_percent"],
                                      "discount_type": d["discount_type"],
                                      "sources": sorted(x["source"] for x in d.get("table_applicable_source") or [] if x["source_type"] == "Warehouse")}
        self.has["Promotion Bonus Buys Master"] = self.promos
        self.users = {}
        for r in shop.list("User", [["name", "like", est.get("user_prefix", "pp-est-") + "%"]], ["name"]):
            d = shop.get("User", r["name"])
            self.users[r["name"]] = {"name": d["name"], "enabled": d["enabled"], "roles": sorted(x["role"] for x in d.get("roles") or [])}
        self.has["User"] = self.users
        self.uperms = {}
        for r in shop.list("User Permission", [["user", "like", est.get("user_prefix", "pp-est-") + "%"]], ["name", "user", "allow", "for_value"]):
            self.uperms[f"{r['user']} | {r['allow']} | {r['for_value']}"] = r
        self.has["User Permission"] = self.uperms
        self.setting = shop.get("Retail Setting", "Retail Setting")


def _row_diff(want, have):
    return {k: (have.get(k), v) for k, v in want.items() if _norm(have.get(k)) != _norm(v)}


def _norm(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return round(float(v), 4)
    return v


def compute(shop, est, rd=None):
    """The diff between the file and the shop: (steps, unchanged, blockers, orphans). A step is
    {op: create|update|delete, dt, name, diff}."""
    rd = rd or Reader(shop, est)
    steps, unchanged, blockers = [], 0, []
    managed = set(est["roles"]["store"]) | set(est["roles"]["region"])
    for dt, name, fields, extra in wanted(est):
        have = rd.has[dt].get(name)
        if dt == "User":
            if have is None:
                steps.append({"op": "create", "dt": dt, "name": name, "diff": dict(fields, roles=extra["roles"])})
                continue
            d = _row_diff(fields, have)
            mine = sorted(set(have["roles"]) & managed)
            if mine != extra["roles"] or not set(extra["roles"]) <= set(have["roles"]):
                d["roles"] = (have["roles"], sorted((set(have["roles"]) - managed) | set(extra["roles"])))
        elif dt == "Promotion Bonus Buys Master":
            if have is None:
                steps.append({"op": "create", "dt": dt, "name": name, "diff": dict(fields, sources=extra["sources"])})
                continue
            d = _row_diff(fields, have)
            if have["sources"] != extra["sources"]:
                d["sources"] = (have["sources"], extra["sources"])
        elif dt == "User Permission":
            if have is None:
                steps.append({"op": "create", "dt": dt, "name": name, "diff": {k: extra[k] for k in ("user", "allow", "for_value")}})
            else:
                unchanged += 1
            continue
        else:
            if have is None:
                steps.append({"op": "create", "dt": dt, "name": name, "diff": dict(fields, **{k: v for k, v in extra.items() if k in ("item", "price_list")})})
                continue
            d = _row_diff(fields, have)
        if d:
            steps.append({"op": "update", "dt": dt, "name": name, "id": have["name"],      # the record's own id (an Item Price's differs from its label)
                          "diff": {k: list(v) if isinstance(v, tuple) else v for k, v in d.items()}})
        else:
            unchanged += 1
    # a user permission an estate user holds that the file does not name is removed by apply (the file is the whole truth for them)
    want_up = {n for dt, n, _f, _e in wanted(est) if dt == "User Permission"}
    for n, r in rd.uperms.items():
        if n not in want_up:
            steps.append({"op": "delete", "dt": "User Permission", "name": n, "diff": {"id": r["name"]}})
    for field, v in est.get("settings", {}).get("Retail Setting", {}).items():
        if int(rd.setting.get(field) or 0) != int(v):
            steps.append({"op": "update", "dt": "Retail Setting", "name": field, "diff": {field: [rd.setting.get(field), v]}})
        else:
            unchanged += 1
    # blockers: what the file names that the shop does not have
    for fmt in {s["print_format"] for s in est["stores"]}:
        if not shop.get("Print Format", fmt):
            blockers.append(f"print format {fmt!r} does not exist in the shop")
    for item in est["items"]:
        if not shop.get("Item", item):
            blockers.append(f"item {item!r} does not exist in the shop")
    for role in managed:
        if not shop.get("Role", role):
            blockers.append(f"role {role!r} does not exist in the shop")
    if not shop.get("POS Profile", est["reference_profile"]):
        blockers.append(f"reference profile {est['reference_profile']!r} does not exist")
    want_names = {(dt, n) for dt, n, _f, _e in wanted(est)}
    orphans = [{"dt": dt, "name": n} for dt in ("Warehouse", "POS Profile", "Price List", "Item Price", "Promotion Bonus Buys Master", "User", "Reason Code Master")
               for n in rd.has[dt] if (dt, n) not in want_names]
    orphans += [{"dt": "Item Price", "name": d} for d in rd.dup_prices]
    return steps, unchanged, blockers, orphans


def apply_steps(shop, est, steps):
    seqs = [m["sequence_number"] or 0 for m in shop.list("Promotion Bonus Buys Master", [], ["sequence_number"])]
    nxt = (max(seqs) + 1) if seqs else 1
    order = ["Reason Code Master", "Price List", "Item Price", "Warehouse", "POS Profile", "Promotion Bonus Buys Master", "User", "User Permission", "Retail Setting"]
    done = 0
    for dt in order:
        for st in [s for s in steps if s["dt"] == dt]:
            name, d = st["name"], st["diff"]
            if st["op"] == "delete":
                shop.delete(dt, d["id"])
            elif dt == "Retail Setting":
                if not os.path.exists(BEFORE):
                    os.makedirs(os.path.dirname(BEFORE), exist_ok=True)
                    json.dump({k: shop.get("Retail Setting", "Retail Setting").get(k) for k in est["settings"]["Retail Setting"]}, open(BEFORE, "w"))
                shop.update("Retail Setting", "Retail Setting", {name: d[name][1]})
            elif st["op"] == "create":
                _create(shop, est, dt, name, d, nxt)
                nxt += dt == "Promotion Bonus Buys Master"
            else:
                _update(shop, dt, st["id"], d)
            done += 1
    return done


def _create(shop, est, dt, name, d, nxt):
    if dt == "Reason Code Master":
        shop.create(dt, {"id": name, "description": name, "reason_type": d["reason_type"], "is_active": 1, "comment_required": 0})
    elif dt == "Price List":
        shop.create(dt, {"price_list_name": name, "currency": d["currency"], "selling": 1, "enabled": 1})
    elif dt == "Item Price":
        shop.create(dt, {"item_code": d["item"], "price_list": d["price_list"], "price_list_rate": d["price_list_rate"], "selling": 1})
    elif dt == "Warehouse":
        shop.create(dt, {"warehouse_name": name[:-len(f" - {est['abbr']}")], "company": d["company"], "parent_warehouse": est["parent_warehouse"],
                         **{k: v for k, v in d.items() if k.startswith("custom_")}})
    elif dt == "POS Profile":
        ref = shop.get("POS Profile", est["reference_profile"])
        doc = {k: v for k, v in ref.items() if k not in _DROP}
        for k, v in list(doc.items()):
            if isinstance(v, list):
                doc[k] = [{kk: vv for kk, vv in row.items() if kk not in _DROP_CHILD} for row in v]
        doc.update(warehouse=d["warehouse"], selling_price_list=d["selling_price_list"], print_format=d["print_format"], disabled=0)
        shop.create(dt, doc, name=name)
    elif dt == "Promotion Bonus Buys Master":
        r = next(r for r in est["regions"] if r["promotion"]["id"] == name)
        shop.create(dt, {"id": name, "description": r["promotion"]["description"], "promotion_type": "Bonus Buys", "discount_type": "Percent",
                         "discount_percent": d["discount_percent"], "minimum_bill_amount": 0, "minimum_quantity": 1, "active": 1,
                         "sequence_number": nxt,
                         "table_applicability": [{"day": x, "enabled": 1, "start_time": "00:00:00", "end_time": "23:59:59"} for x in DAYS],
                         "table_applicable_source": [{"source_type": "Warehouse", "source": w} for w in d["sources"]]})
    elif dt == "User":
        shop.create(dt, {"email": name, "first_name": name.split("@")[0], "send_welcome_email": 0, "user_type": "System User",
                         "custom_is_desk_user": 1, "enabled": 1, "roles": [{"role": r} for r in d["roles"]]})
    elif dt == "User Permission":
        shop.create(dt, {"user": d["user"], "allow": d["allow"], "for_value": d["for_value"]})


def _update(shop, dt, name, d):
    """``d`` is {field: [have, want]}: write the wanted values; the two list-shaped fields become their child tables."""
    want = {k: v[1] for k, v in d.items()}
    if "sources" in want:
        want["table_applicable_source"] = [{"source_type": "Warehouse", "source": w} for w in want.pop("sources")]
    if "roles" in want:
        want["roles"] = [{"role": r} for r in want["roles"]]
    shop.update(dt, name, want)


def remove_all(shop, est):
    """Take the estate out, in the reverse order. Retire what a booked sale points at."""
    rd = Reader(shop, est)
    out = {"removed": 0, "retired": [], "kept": []}
    retire = {"Warehouse": {"disabled": 1}, "POS Profile": {"disabled": 1}, "Price List": {"enabled": 0}, "User": {"enabled": 0},
              "Reason Code Master": {"is_active": 0}, "Promotion Bonus Buys Master": {"active": 0}, "Item Price": None}
    for dt in ("User Permission", "Promotion Bonus Buys Master", "POS Profile", "Item Price", "Warehouse", "Price List", "User", "Reason Code Master"):
        for key, row in list(rd.has[dt].items()):
            real = row["name"]
            if shop.delete(dt, real):
                out["removed"] += 1
            elif retire.get(dt):
                shop.update(dt, real, retire[dt])
                out["retired"].append(f"{dt}: {key}")
            else:
                out["kept"].append(f"{dt}: {key}")           # cannot be deleted and has no 'retired' state: say so
    if os.path.exists(BEFORE):
        shop.update("Retail Setting", "Retail Setting", json.load(open(BEFORE)))
        os.remove(BEFORE)
        out["switches_put_back"] = True
    return out


def main(argv=None):
    argv = argv or sys.argv[1:]
    if len(argv) < 3 or argv[0] not in ("plan", "apply", "verify", "remove") or argv[1] != "--estate":
        sys.exit(__doc__)
    cmd, est = argv[0], json.load(open(argv[2]))
    shop = Shop(os.environ["PP_BASE"], os.environ["PP_KEY"], os.environ["PP_SECRET"])
    if cmd == "remove":
        print(json.dumps(remove_all(shop, est)))
        return 0
    steps, unchanged, blockers, orphans = compute(shop, est)
    summary = {"create": sum(s["op"] == "create" for s in steps), "update": sum(s["op"] == "update" for s in steps),
               "delete": sum(s["op"] == "delete" for s in steps), "unchanged": unchanged, "blockers": blockers, "orphans": len(orphans)}
    for s in steps:
        print(f"  {s['op']:<7} {s['dt']}: {s['name']}  {json.dumps(s['diff'], default=str)[:600]}")
    if blockers and cmd in ("apply",):
        print(json.dumps(summary))
        sys.exit("REFUSED: " + "; ".join(blockers))
    if cmd == "apply":
        apply_steps(shop, est, steps)
        summary["applied"] = len(steps)
    if cmd == "verify":
        for o in orphans:
            print(f"  orphan  {o['dt']}: {o['name']}  (not in the file)")
        summary["differences"] = len(steps) + len(orphans)
    print(json.dumps(summary))
    if cmd == "verify" and (steps or orphans or blockers):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
