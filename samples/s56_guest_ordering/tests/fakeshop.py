"""A stand-in for the retailer's iVendNext as S56's service reads it, as the app's own user: the settings with their
store rows, the code records and the shop's ``modified`` check, the register, its items, their choice rows and the
choice groups, the line pricer, and the till's open-check door (``floor_status``; ``check_open`` and
``check_add_lines`` keeping their first answer for a key and refusing the same key with other arguments). It is the
shop as S56 reads it, never the shop's own rules beyond these."""

import copy
import datetime
import itertools

import app

CO = "Bistro Co"
STORE = "Bistro - BC"
REG = "Bistro R1"
T12, T14 = "FP-T12", "FP-T14"
LABELS = {T12: "Table 12", T14: "Table 14"}
SITE = "bistro.example.com"
SECRET = "s3cret-code"
PAGE = "https://guest-ordering.example.app"

ITEMS = [
    {"name": "LATTE", "item_name": "Latte", "item_group": "Drinks", "custom_mpos_option_only": 0},
    {"name": "BURGER", "item_name": "Burger", "item_group": "Mains", "custom_mpos_option_only": 0},
    {"name": "SALAD", "item_name": "Green salad", "item_group": "Mains", "custom_mpos_option_only": 0},
    {"name": "OAT", "item_name": "Oat milk", "item_group": "Drinks", "custom_mpos_option_only": 1},
    {"name": "GIFT", "item_name": "Gift card", "item_group": "Mains", "custom_mpos_option_only": 0, "custom_is_gift_card": 1},
]
ROWS = [   # the dishes' Cross Selling Product Detail rows
    {"parent": "LATTE", "idx": 1, "item_code": "OAT", "item_name": "Oat milk", "price_type": "Amount", "price": 0.6,
     "discount_type": "", "discount": 0, "custom_mpos_option_group": "Milk"},
    {"parent": "LATTE", "idx": 2, "item_code": "COW", "item_name": "Whole milk", "price_type": "System Generated",
     "price": 0, "discount_type": "", "discount": 0, "custom_mpos_option_group": "Milk"},
    {"parent": "LATTE", "idx": 3, "item_code": "SHOT", "item_name": "Extra shot", "price_type": "System Generated",
     "price": 0, "discount_type": "Percentage", "discount": 50, "custom_mpos_option_group": "Extras"},
    {"parent": "BURGER", "idx": 1, "item_code": "CHEESE", "item_name": "Cheese", "price_type": "Amount", "price": 1.0,
     "discount_type": "", "discount": 0, "custom_mpos_option_group": "Toppings"},
    {"parent": "BURGER", "idx": 2, "item_code": "BACON", "item_name": "Bacon", "price_type": "Amount", "price": 1.5,
     "discount_type": "Amount", "discount": 0.5, "custom_mpos_option_group": "Toppings"},
]
GROUPS = {"Milk": {"name": "Milk", "display_name": "Milk", "min_picks": 1, "max_picks": 1, "enabled": 1},
          "Extras": {"name": "Extras", "display_name": "Extras", "min_picks": 0, "max_picks": 2, "enabled": 1},
          "Toppings": {"name": "Toppings", "display_name": "Toppings", "min_picks": 0, "max_picks": 2, "enabled": 1}}
PRICES = {"LATTE": 3.2, "BURGER": 11.0, "SALAD": 7.5, "COW": 0.0, "SHOT": 0.8}


def settings(**row):
    return {"name": CO, "company": CO, "modified": "2026-10-29 09:00:00.000001",
            "stores": [dict({"parent": CO, "store": STORE, "register": REG, "tables_on": 1, "kiosk_on": 1,
                             "course": "", "most_lines": 0, "most_qty": 0}, **row)]}


def code(name, kind="Table", place=T12, number=0, kiosk_name="", **kw):
    c = dict({"name": name, "kind": kind, "store": STORE, "place": place if kind == "Table" else "",
              "place_label": LABELS.get(place, "") if kind == "Table" else "", "kiosk_name": kiosk_name,
              "number": number, "link": "", "qr": "", "made_for": "", "modified": "2026-10-29 10:00:00.000001"}, **kw)
    return c


class FakeTenant:
    def __init__(self, codes=(), settings_=None, refuse=None, door_refuse=None, lose=None, open_checks=(),
                 groups_on_register=("Drinks", "Mains"), stale_code=0):
        self.settings = {CO: settings_ or settings()}
        self.codes = {c["name"]: copy.deepcopy(c) for c in codes}
        self.register = {"name": REG, "company": CO, "currency": "EUR", "selling_price_list": "Menu", "customer": "Walk-in",
                         "warehouse": STORE, "item_groups": [{"item_group": g} for g in groups_on_register]}
        self.refuse, self.door_refuse, self.lose, self.stale_code = refuse, door_refuse, dict(lose or {}), stale_code
        self.keys = {}                   # the door's memory: (verb, key) → (arguments, answer)
        self.checks = {c["check"]: dict(c, lines=list(c.get("lines") or [])) for c in open_checks}
        self.n = itertools.count(1)
        self.clock = datetime.datetime(2026, 10, 29, 19, 0, 0)
        self.calls, self.sent = [], []
        self.slow, self.tick = set(), None

    def _gate(self, what):
        self.calls.append(what)
        if self.refuse and what.startswith(self.refuse[0]):
            raise app.TenantError(f"{what} -> HTTP {self.refuse[1]}", self.refuse[1], *self.refuse[2:])

    # ── the record API ──
    def doc(self, doctype, name):
        self._gate(f"GET {doctype}")
        if doctype.endswith(" Code"):
            if name not in self.codes:
                raise app.TenantError("404", 404)
            return copy.deepcopy(self.codes[name])
        if doctype == "POS Profile" and name == REG:
            return copy.deepcopy(self.register)
        raise app.TenantError("404", 404)

    def rows(self, doctype, fields, filters, parent=None, limit=500):
        self._gate(f"LIST {doctype}")
        if doctype.endswith(" Store"):
            src = [dict(r) for s in self.settings.values() for r in s["stores"]]
        elif doctype == "Item":
            src = [dict({"custom_is_gift_card": 0}, **dict(i, is_sales_item=1, disabled=0, has_variants=0)) for i in ITEMS]
        elif doctype == "Cross Selling Product Detail":
            assert parent == "Item"
            src = [dict(r) for r in ROWS]
        elif doctype == "Retail Option Group":
            src = [dict(g) for g in GROUPS.values()]
        else:
            raise app.TenantError("403", 403)
        out = []
        for r in src:
            ok = True
            for f, op, v in filters:
                if op == "=" and r.get(f) != v or op == "in" and r.get(f) not in v or op == "is" and not r.get(f):
                    ok = False
            if ok:
                out.append({k: r.get(k) for k in fields})
        return out[:limit]

    def update(self, doctype, name, body):
        self._gate(f"PUT {doctype}")
        self.sent.append(copy.deepcopy(body))
        rec = self.codes[name]
        if self.stale_code:                   # the manager saved the record a moment before
            self.stale_code -= 1
            rec["modified"] = "2026-10-29 10:00:01.000001"
        if "modified" in body and body["modified"] != rec.get("modified"):
            raise app.TenantError("PUT -> HTTP 417", 417, app.STALE)
        rec.update({k: v for k, v in body.items() if k != "modified"})
        self.clock += datetime.timedelta(seconds=1)
        rec["modified"] = self.clock.isoformat(sep=" ") + ".000001"
        return copy.deepcopy(rec)

    # ── the till's partner API ──
    def call(self, verb, body=None, query=None):
        self._gate(f"CALL {verb}")
        self.sent.append(copy.deepcopy(body or query))
        if verb == "get_item_details":
            args = body["args"]
            assert "rate" not in args and "price_list_rate" not in args
            if args["item_code"] in self.slow and self.tick is not None:
                self.tick.t += 6                                    # a slow answer: the service's time budget runs out
            return {"item_code": args["item_code"], "price_list_rate": PRICES.get(args["item_code"], 0.0)}   # no row: 0.0
        if verb == "floor_status":
            places = []
            for p in LABELS:
                cs = [c for c in self.checks.values() if c.get("place") == p]
                places.append({"place": p, "label": LABELS[p], "status": "seated" if cs else "free",
                               "checks": [{"check": c["check"], "version": 1,
                                           "status": "paying" if c.get("paying") else "seated"} for c in cs]})
            tabs = [{"check": c["check"], "label": c.get("label")} for c in self.checks.values() if not c.get("place")]
            return {"store": query["store"], "sections": [], "places": places, "tabs": tabs}
        if self.door_refuse and verb == self.door_refuse[0]:
            kind, code = self.door_refuse[1:]
            raise app.TenantError(f"{verb} -> HTTP {code}", code, kind)
        if verb not in ("check_open", "check_add_lines"):
            raise app.TenantError("404", 404)
        key = body["key"]
        args = {k: v for k, v in body.items() if k != "key"}
        if (verb, key) in self.keys:
            first, answer = self.keys[(verb, key)]
            if first != args:
                raise app.TenantError(f"{verb} -> HTTP 417", 417, "CheckRequestError")
        elif verb == "check_open":
            name = f"CHK-{next(self.n):04d}"
            self.checks[name] = {"check": name, "place": body.get("place"), "label": body.get("label"),
                                 "covers": body.get("covers"), "source_ref": body.get("source_ref"), "lines": []}
            answer = {"check": name, "version": 1}
            self.keys[(verb, key)] = (args, answer)
        else:
            check = self.checks.get(body["check"])
            if check is None:
                raise app.TenantError(f"{verb} -> HTTP 417", 417, "CheckNotOpenError")
            for ln in body["lines"]:
                assert not set(ln) & {"rate", "price", "amount", "price_list_rate", "discount", "concession_note"}
                check["lines"].append(dict(ln, sent=0))
            answer = {"check": body["check"], "version": 2}
            self.keys[(verb, key)] = (args, answer)
        if self.lose.get(verb):
            self.lose[verb] -= 1
            raise app.TenantError(f"{verb} -> TimeoutError")        # it happened; the answer was lost
        return copy.deepcopy(answer)
