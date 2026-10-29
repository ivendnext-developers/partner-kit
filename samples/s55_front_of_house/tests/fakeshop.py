"""A stand-in for the shop as S55's service reads it, as the app's own user: the settings with their store rows and the
shop's ``modified`` check, reservations and waiting parties (the guest's fields kept apart and never answered, as the
shop leaves out a field the app's user may not read), and the till's open-check door (``check_open`` keeping its
first answer for a key, refusing the same key with other arguments; ``floor_status``). It is the shop as S55 reads it,
never the shop's own rules beyond these."""

import copy
import datetime
import itertools

import app

CO = "Bistro Co"
STORE = "Bistro - BC"
REG = "Bistro R1"
T12, T14 = "FP-T12", "FP-T14"
LABELS = {T12: "Table 12", T14: "Table 14"}
GUEST = {"guest_name", "phone", "customer", "notes"}       # the fields only the host role reads


def settings(**row):
    return {"name": CO, "company": CO, "run_started": "", "modified": "2026-10-29 09:00:00.000001",
            "stores": [dict({"parent": CO, "store": STORE, "register": REG, "minutes": 90, "second_check": 0,
                             "no_show_deposit": "Keep it"}, **row)]}


def booking(name, time_, place=T12, status="Booked", date="2026-10-29", party=4, **kw):
    return dict({"name": name, "status": status, "store": STORE, "booking_date": date, "booking_time": time_,
                 "minutes": None, "party": party, "place": place, "place_label": LABELS.get(place, place),
                 "deposit_sale": None, "deposit_amount": None, "check_name": "", "seat_key": "", "seat_request": "",
                 "app_note": "", "guest_name": "Ana Lima", "phone": "+351 912 000 111", "customer": "CUST-ANA",
                 "notes": "a birthday", "modified": "2026-10-29 10:00:00.000001"}, **kw)


def waiting(name, place=T14, party=2, status="Waiting", **kw):
    return dict({"name": name, "status": status, "store": STORE, "party": party, "place": place,
                 "place_label": LABELS.get(place, place), "check_name": "", "seat_key": "", "seat_request": "",
                 "app_note": "", "guest_name": "Ben Ode", "phone": "+44 7700 900123",
                 "modified": "2026-10-29 19:00:00.000001"}, **kw)


class FakeTenant:
    def __init__(self, reservations=(), waitlist=(), settings_=None, clock="2026-10-29 19:00:00", refuse=None,
                 door_refuse=None, lose_open=0, stale_seat=0, open_checks=()):
        self.settings = {CO: settings_ or settings()}
        self.res = {r["name"]: copy.deepcopy(r) for r in reservations}
        self.wait = {w["name"]: copy.deepcopy(w) for w in waitlist}
        self.clock = datetime.datetime.fromisoformat(clock)
        self.refuse, self.door_refuse, self.lose_open, self.stale_seat = refuse, door_refuse, lose_open, stale_seat
        self.keys = {}                   # the door's memory: key → (arguments, check)
        self.checks = [dict(c) for c in open_checks]     # {"check", "place"} already open on the floor
        self.n = itertools.count(1)
        self.calls, self.sent = [], []

    def _tick(self) -> str:
        self.clock += datetime.timedelta(seconds=1)
        return self.clock.isoformat(sep=" ") + ".000001"

    def _gate(self, what):
        self.calls.append(what)
        if self.refuse and what.startswith(self.refuse[0]):
            raise app.TenantError(f"{what} -> HTTP {self.refuse[1]}", self.refuse[1], *self.refuse[2:])

    def _table(self, doctype):
        if doctype.endswith(" Reservation"):
            return self.res
        if doctype.endswith(" Waitlist Entry"):
            return self.wait
        if doctype.endswith(" Settings"):
            return self.settings
        raise app.TenantError("404", 404)

    @staticmethod
    def _as_app(rec):
        """The record as the app's user reads it: the guest's fields are left out."""
        return {k: v for k, v in copy.deepcopy(rec).items() if k not in GUEST}

    # ── the record API ──
    def doc(self, doctype, name):
        self._gate(f"GET {doctype}")
        t = self._table(doctype)
        if name not in t:
            raise app.TenantError("404", 404)
        return self._as_app(t[name])

    def rows(self, doctype, fields, filters, parent=None):
        self._gate(f"LIST {doctype}")
        if doctype.endswith(" Store"):
            src = [dict(r) for s in self.settings.values() for r in s["stores"]]
        else:
            src = [self._as_app(r) for r in self._table(doctype).values()]
        out = []
        for r in src:
            ok = True
            for f, op, v in filters:
                if op == "=" and r.get(f) != v or op == "in" and r.get(f) not in v:
                    ok = False
            if ok:
                out.append({k: r.get(k) for k in fields if k not in GUEST})
        return out

    def update(self, doctype, name, body):
        self._gate(f"PUT {doctype}")
        self.sent.append(copy.deepcopy(body))
        t = self._table(doctype)
        rec = t[name]
        if "modified" in body:
            if self.stale_seat and "seat_key" in body:
                self.stale_seat -= 1
                rec.update(seat_key="other-key", seat_request=app.json.dumps(
                    {"key": "other-key", "store": STORE, "pos_profile": REG, "place": rec.get("place"),
                     "covers": rec.get("party"), "label": f"{name} · {rec.get('party')}", "source": "front_of_house",
                     "source_ref": name}, sort_keys=True))
                rec["modified"] = self._tick()
                raise app.TenantError("PUT -> HTTP 417", 417, app.STALE)
            if body["modified"] != rec.get("modified"):
                raise app.TenantError("PUT -> HTTP 417", 417, app.STALE)
        rec.update({k: v for k, v in body.items() if k != "modified"})
        rec["modified"] = self._tick()
        return self._as_app(rec)

    # ── the till's open-check door ──
    def call(self, verb, body=None, query=None):
        self._gate(f"CALL {verb}")
        self.sent.append(copy.deepcopy(body or query))
        if verb == "floor_status":
            places = []
            for p in LABELS:
                cs = [c for c in self.checks if c["place"] == p]
                places.append({"place": p, "label": LABELS[p], "status": "seated" if cs else "free",
                               "checks": [{"check": c["check"]} for c in cs]})
            return {"store": query["store"], "sections": [], "places": places, "tabs": []}
        if verb != "check_open":
            raise app.TenantError("404", 404)
        if self.door_refuse:
            kind, code, said = self.door_refuse
            raise app.TenantError(f"{verb} -> HTTP {code}", code, kind, said)
        key = body["key"]
        args = {k: v for k, v in body.items() if k != "key"}
        if key in self.keys:
            first_args, check = self.keys[key]
            if first_args != args:
                raise app.TenantError(f"{verb} -> HTTP 417", 417, "CheckRequestError",
                                      "That key was already used for another request.")
        else:
            check = {"check": f"CHK-{next(self.n):04d}", "version": 1, "status": "open", "store": body["store"],
                     "place": body.get("place"), "covers": body.get("covers"), "lines": []}
            self.keys[key] = (args, check)
            self.checks.append({"check": check["check"], "place": body.get("place")})
        if self.lose_open:
            self.lose_open -= 1
            raise app.TenantError(f"{verb} -> TimeoutError")        # the check opened; the answer was lost
        return copy.deepcopy(check)
