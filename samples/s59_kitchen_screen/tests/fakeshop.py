"""A stand-in for the retailer's iVendNext as S59's service reads it, as the app's own user: the settings with their
store rows, the screen records and the shop's ``modified`` check, and the till's station-ticket door
(``station_tickets``, ``station_ticket_move`` one step at a time with ``already`` for the same step, a skip or a step
back refused, another store's ticket not found) and item availability (``item_availability``,
``set_item_availability``, answering for ANY store, as the till does: the till does not fence them to a user's stores).
It is the shop as S59 reads it, never the shop's own rules beyond these."""

import copy

import app

CO = "Bistro Co"
STORE, OTHER = "Bistro - BC", "Harbour - BC"
SITE = "bistro.example.com"
SECRET = "s3cret-link"
PAGE = "https://kitchen-screen.example.app"
GRILL, BAR, FRY = "Grill", "Bar", "Fryer"
STEP = {"new": "started", "started": "ready", "ready": "bumped"}


def settings(**row):
    return {"name": CO, "company": CO, "modified": "2026-10-30 09:00:00.000001",
            "stores": [dict({"parent": CO, "store": STORE, "sold_out_on": 1, "warn_min": 0, "late_min": 0, "look": "Dark",
                             "accent": "", "language": "English", "tables_on_board": 0,
                             "slip_size": "Standard"}, **row)]}


def screen(name, kind="Station", stations=(GRILL,), store=STORE, number=0, title="Grill", **kw):
    return dict({"name": name, "title": title, "kind": kind, "store": store,
                 "stations": [{"station": s} for s in stations], "number": number, "link": "", "made_for": "",
                 "modified": "2026-10-30 10:00:00.000001"}, **kw)


def line(code, name, qty=1, under=None, note="", guest="", course="", allergens=""):
    return {"item_code": code, "item_name": name, "uom": "Nos", "qty": qty, "note": note, "under": under, "guest": guest,
            "course": course, "allergens": allergens}


def ticket(order, n, station, lines, kind="send", source="sale", call="42", state="new", store=STORE,
           sent_at="2026-10-30 19:00:00.000001", state_at=None):
    return {"store": store, "kitchen_order": order, "ticket": n, "station": station, "kind": kind, "source": source,
            "call_number": call, "service_mode": "Dine In" if source == "check" else "Take Away", "till": "Till 2",
            "sent_at": sent_at, "state": state, "state_at": state_at, "lines": lines}


def lunch():
    """Two orders: a counter sale (call 42) of a burger with cheese to the grill and fries to the fryer; a table's check
    (Table 12) of a steak to the grill and a beer to the bar; and a ticket of another store."""
    return [
        ticket("ko1", 1, GRILL, [line("BURGER", "Burger", 2, allergens="Allergens: sesame, gluten"),
                                 line("CHEESE", "Extra cheese", 1, under=0)]),
        ticket("ko1", 2, FRY, [line("FRIES", "Fries", 3)]),
        ticket("ko2", 1, GRILL, [line("STEAK", "Steak", 1, note="medium rare", guest="2", course="Mains")],
               source="check", call="Table 12", sent_at="2026-10-30 19:01:00.000001"),
        ticket("ko2", 2, BAR, [line("BEER", "Beer", 2, guest="1", course="Drinks")], source="check", call="Table 12",
               sent_at="2026-10-30 19:01:00.000001"),
        ticket("kx9", 1, GRILL, [line("BURGER", "Burger", 1)], store=OTHER, call="7"),
    ]


class FakeTenant:
    def __init__(self, screens=(), settings_=None, tickets=None, refuse=None, door_refuse=None, stale=0, sold=()):
        self.settings = {CO: settings_ or settings()}
        self.screens = {s["name"]: copy.deepcopy(s) for s in screens}
        self.tickets = copy.deepcopy(lunch() if tickets is None else tickets)
        self.refuse, self.door_refuse, self.stale = refuse, door_refuse, stale
        self.sold = {(c, STORE) for c in sold}
        self.calls, self.sent = [], []

    def _gate(self, what):
        self.calls.append(what)
        if self.refuse and what.startswith(self.refuse[0]):
            raise app.TenantError(f"{what} -> HTTP {self.refuse[1]}", self.refuse[1], *self.refuse[2:])

    # ── the record API ──
    def doc(self, doctype, name):
        self._gate(f"doc {doctype}")
        if doctype == "PP KSC Screen" or doctype.endswith(" Screen"):
            if name not in self.screens:
                raise app.TenantError("not found", 404)
            out = copy.deepcopy(self.screens[name])
            if self.stale:                          # someone saves the screen just after this read
                self.stale -= 1
                self.screens[name]["modified"] += "9"
            return out
        raise app.TenantError("not found", 404)

    def rows(self, doctype, fields, filters, parent=None, limit=500):
        self._gate(f"rows {doctype}")
        if doctype.endswith(" Store"):
            store = filters[0][2]
            return [{k: r.get(k) for k in fields} for s in self.settings.values() for r in s["stores"] if r["store"] == store]
        return []

    def update(self, doctype, name, body):
        self._gate(f"update {doctype}")
        s = self.screens[name]
        if "modified" in body and body["modified"] != s["modified"]:     # the shop checks it only when it is sent
            raise app.TenantError("stale", 417, "TimestampMismatchError")
        self.sent.append((name, dict(body)))
        s.update({k: v for k, v in body.items() if k != "modified"})
        s["modified"] += "1"
        return copy.deepcopy(s)

    # ── the till's partner API ──
    def call(self, verb, body=None, query=None):
        self._gate(verb)
        if self.door_refuse and verb == self.door_refuse[0]:
            raise app.TenantError(f"{verb} -> HTTP {self.door_refuse[1]}", self.door_refuse[1], *self.door_refuse[2:])
        if verb == "station_tickets":
            store = query["store"]
            return {"store": store, "station": None, "as_of": "2026-10-30 19:05:30.000001", "event": "mpos_station_ticket",
                    "tickets": [{k: v for k, v in t.items() if k != "store"} for t in self.tickets if t["store"] == store]}
        if verb == "station_ticket_move":
            self.sent.append((verb, dict(body)))
            for t in self.tickets:
                if t["store"] == body["store"] and t["kitchen_order"] == body["kitchen_order"] and t["ticket"] == body["ticket"]:
                    if t["state"] == body["state"]:
                        return {"ok": True, "already": True, "ticket": dict(t)}
                    if STEP.get(t["state"]) != body["state"]:
                        raise app.TenantError("step", 417, "TicketStepError")
                    t["state"], t["state_at"] = body["state"], "2026-10-30 19:05:31.000001"
                    return {"ok": True, "already": False, "ticket": dict(t)}
            raise app.TenantError("not found", 404, "TicketNotFoundError")
        if verb == "item_availability":
            wh = query["warehouse"]
            return [{"item_code": c, "warehouse": w, "available": False, "reason": "sold_out", "sold_out": 1,
                     "until": None, "from": None, "to": None} for c, w in sorted(self.sold) if w == wh]
        if verb == "set_item_availability":
            self.sent.append((verb, dict(body)))
            key = (body["item_code"], body["warehouse"])
            (self.sold.add if body["sold_out"] else self.sold.discard)(key)
            return {"item_code": key[0], "warehouse": key[1], "available": not body["sold_out"]}
        raise AssertionError(f"S59 never calls {verb}")
