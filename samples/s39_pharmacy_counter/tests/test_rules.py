"""S39's pure core: each rule a shop fills, the strictest of an item's schedules, a prescription's fills and quantity, the
dispensings that count and the statuses the shop gives them back."""
import datetime
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rxrules as R  # noqa: E402

P = "PP RXC"
TODAY = datetime.date(2026, 10, 22)


def sched(name, **k):
    base = {"name": name, "axis": k.pop("axis", name), "needs_prescription": 0, "pharmacist_only": 0, "dispensary_only": 0,
            "validity_days": 0, "max_fills": 0, "qty_cap": 0, "freq_qty": 0, "freq_days": 0, "needs_id_number": 0,
            "needs_birth_date": 0, "needs_authority": 0, "needs_consent": 0, "returnable": 0, "return_gives_back": 0, "needs_directions": 0,
            "own_sale_without_rx": 0}
    base.update(k)
    return base


SCHEDULES = R.schedules_of([
    sched("POM", axis="Prescription", needs_prescription=1, pharmacist_only=1, dispensary_only=1, validity_days=90,
          return_gives_back=1),
    sched("CD2", axis="Controlled", needs_prescription=1, pharmacist_only=1, validity_days=30, max_fills=1, qty_cap=20,
          freq_qty=40, freq_days=30, needs_id_number=1, needs_birth_date=1, return_gives_back=1),
    sched("PMED", axis="Pharmacy", qty_cap=2, returnable=1, return_gives_back=1),
    sched("GHA", axis="Act 489", needs_prescription=1, validity_days=60, returnable=1, return_gives_back=1),
    sched("GH1019", axis="Act 1019", qty_cap=5, validity_days=14, returnable=1, return_gives_back=0),
    sched("KEP1", axis="KE Poisons", returnable=1, own_sale_without_rx=1),
    sched("DATED", axis="Register", needs_prescription=1, register_books_rx_date=1),
])


def rule(*names):
    return R.strictest([SCHEDULES[n] for n in names])


def line(item, qty, n=1, group="G", linked=False):
    return {"n": n, "item": item, "group": group, "qty": qty, "uom": "", "linked": linked, "parent": ""}


def ctx(lines, customer="Ann", details=None, source="till", sale_ref="s1", stage="sale"):
    return {"source": source, "stage": stage, "sale_ref": sale_ref, "operator": "ph@shop", "customer": customer,
            "pos_profile": "Dispensary", "pos_opening": "DAY-1", "return_of": "", "doctype": "", "name": "",
            "details": {f"{P} {k}": v for k, v in (details or {}).items()}, "lines": lines}


def rx(name, item, qty, customer="Ann", fills=1, written="2026-10-20", retained=False, active=True, directions=""):
    return {"name": name, "reference": f"PAPER-{name}", "customer": customer, "date_written": written, "fills": fills,
            "retained": retained, "active": active, "prescriber": "Dr Who",
            "items": [{"item": item, "qty": qty, "directions": directions}]}


def disp(name, lines, status=R.RESERVED, seq=1, sale_ref="old", day=TODAY, fp=None):
    return {"name": name, "seq": seq, "status": status, "source": "till", "sale_ref": sale_ref, "document_type": "",
            "document": "", "pos_opening": "DAY-0", "pos_invoice": "", "day": day, "lines": lines,
            "fingerprints": fp or {}}


PHARMACIST = {"active": True, "valid_until": datetime.date(2027, 1, 1)}


def shop(c, rules, rxs=(), dispensings=(), pharmacist=PHARMACIST, walk_in=False, fields=None, directions=None,
         items=None, returned_from=()):
    return {"rules": rules, "qty": [x["qty"] for x in c["lines"]], "items": items or {},
            "group_directions": directions or [False] * len(c["lines"]), "walk_in": walk_in, "pharmacist": pharmacist,
            "customer_fields": fields if fields is not None else {"id_number": "ID-1", "birth_date": "1980-01-01"},
            "rxs": {r["name"]: r for r in rxs}, "dispensings": list(dispensings), "returned_from": list(returned_from)}


def decide(c, s, route="dispensary"):
    return R.decide(c, route, s, TODAY, P)


class Schedules(unittest.TestCase):
    def test_the_strictest_of_two_axes_applies(self):
        r = rule("GHA", "GH1019")
        self.assertTrue(r["rx"])
        self.assertEqual((r["validity"], r["qty_cap"]), (14, 5))
        self.assertTrue(r["returnable"])
        self.assertFalse(r["gives_back"])          # a give-back only when every schedule says so

    def test_a_limit_that_is_not_a_whole_positive_number_is_no_limit(self):
        s = R.schedules_of([sched("X", validity_days=-3, max_fills=1.5, qty_cap="9")])["X"]
        self.assertEqual((s["validity"], s["max_fills"], s["qty_cap"]), (0, 0, 0))

    def test_an_items_own_rows_win_one_per_axis_the_latest_effective(self):
        rows = R.item_schedules_of([{"parent": "T", "schedule": "GHA", "effective_from": "2020-01-01"},
                                    {"parent": "T", "schedule": "POM", "effective_from": "2026-01-01"},
                                    {"parent": "T", "schedule": "GH1019", "effective_from": "2027-01-01"}], TODAY)
        sch = dict(SCHEDULES)
        sch["POM"] = dict(sch["POM"], axis="Act 489")          # POM reclassifies GHA on the same axis from 2026
        names = [s["name"] for s in R.schedules_for("T", "G", {}, rows, {}, sch)]
        self.assertEqual(names, ["POM"])                        # GH1019 is effective only next year

    def test_a_variants_own_row_never_hides_its_templates_class_on_another_axis(self):
        rows = R.item_schedules_of([{"parent": "TPL", "schedule": "GHA", "effective_from": None},
                                    {"parent": "V1", "schedule": "GH1019", "effective_from": None}], TODAY)
        items = {"V1": {"template": "TPL", "stock_uom": "Nos", "directions": ""}}
        self.assertEqual([s["name"] for s in R.schedules_for("V1", "G", items, rows, {}, SCHEDULES)], ["GH1019", "GHA"])
        groups = R.groups_of([{"name": "All", "lft": 1, "rgt": 10}, {"name": "Med", "lft": 2, "rgt": 7, "pp_rxc_schedule": "POM"}], P)
        rows = R.item_schedules_of([{"parent": "X", "schedule": "PMED", "effective_from": None}], TODAY)
        self.assertEqual([s["name"] for s in R.schedules_for("X", "Med", {}, rows, groups, SCHEDULES)], ["PMED", "POM"])

    def test_a_variant_reads_its_templates_rows_then_the_nearest_group(self):
        rows = R.item_schedules_of([{"parent": "TPL", "schedule": "CD2", "effective_from": None}], TODAY)
        items = {"V1": {"template": "TPL", "stock_uom": "Nos", "directions": ""}}
        self.assertEqual([s["name"] for s in R.schedules_for("V1", "G", items, rows, {}, SCHEDULES)], ["CD2"])
        groups = R.groups_of([{"name": "All", "lft": 1, "rgt": 10}, {"name": "Med", "lft": 2, "rgt": 7, "pp_rxc_schedule": "POM"},
                              {"name": "Tabs", "lft": 3, "rgt": 4}], P)
        self.assertEqual([s["name"] for s in R.schedules_for("X", "Tabs", {}, {}, groups, SCHEDULES)], ["POM"])
        self.assertEqual(R.schedules_for("X", "All", {}, {}, groups, SCHEDULES), [])

    def test_a_schedule_the_shop_no_longer_holds_is_left_out(self):
        rows = R.item_schedules_of([{"parent": "T", "schedule": "GONE", "effective_from": None}], TODAY)
        self.assertEqual(R.schedules_for("T", "G", {}, rows, {}, SCHEDULES), [])

    def test_a_unit_with_no_conversion_is_none_and_a_strip_counts_in_stock_units(self):
        items = {"A": {"template": "", "stock_uom": "Nos", "directions": ""}, "V": {"template": "A", "stock_uom": "Nos",
                                                                              "directions": ""}}
        self.assertEqual(R.to_stock({"item": "A", "qty": 2, "uom": "Strip"}, items, {("A", "Strip"): 7.0}), 14)
        self.assertEqual(R.to_stock({"item": "V", "qty": 2, "uom": "Strip"}, items, {("A", "Strip"): 7.0}), 14)
        self.assertIsNone(R.to_stock({"item": "A", "qty": 2, "uom": "Box"}, items, {}))

    def test_an_unscheduled_line_in_an_unknown_unit_never_breaks_the_cap(self):
        c = ctx([line("PARA", 2, 1), line("BREAD", 1, 2)])
        s = shop(c, [rule("PMED"), None])
        s["qty"] = [2, None]
        self.assertEqual(decide(c, s)["verdict"], "allow")


class WhoMaySell(unittest.TestCase):
    def test_a_counter_assistant_is_stopped_and_a_pharmacist_served(self):
        c = ctx([line("AMOX", 21)], details={"Rx Number": "RX1"})
        out = decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21)], pharmacist=None))
        self.assertEqual(out["verdict"], "refuse")
        self.assertIn("Only a pharmacist may sell this.", out["reason"])
        self.assertEqual(decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21)]))["verdict"], "allow")

    def test_a_pharmacist_past_valid_until_is_refused_on_the_day_after(self):
        c = ctx([line("AMOX", 21)], details={"Rx Number": "RX1"})
        lapsed = {"active": True, "valid_until": TODAY - datetime.timedelta(days=1)}
        out = decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21)], pharmacist=lapsed))
        self.assertIn("licence ran out on 2026-10-21", out["reason"])
        today = {"active": True, "valid_until": TODAY}
        self.assertEqual(decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21)], pharmacist=today))["verdict"], "allow")

    def test_a_delegate_is_not_a_pharmacist_until_the_rule_is_ruled(self):
        c = ctx([line("AMOX", 21)], details={"Rx Number": "RX1"})
        out = decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21)], pharmacist=dict(PHARMACIST, delegate=True)))
        self.assertIn("Only a pharmacist", out["reason"])

    def test_an_inactive_pharmacist_is_no_pharmacist(self):
        c = ctx([line("AMOX", 21)], details={"Rx Number": "RX1"})
        out = decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21)], pharmacist={"active": False,
                                                                                     "valid_until": TODAY}))
        self.assertIn("Only a pharmacist", out["reason"])

    def test_the_front_sends_prescription_medicine_to_the_dispensary(self):
        c = ctx([line("BREAD", 1, 1), line("AMOX", 21, 2)], details={"Rx Number": "RX1"})
        out = decide(c, shop(c, [None, rule("POM")], [rx("RX1", "AMOX", 21)]), route="front")
        self.assertEqual(out["reason"], "Line 2: AMOX: Sell this at the dispensary.")

    def test_the_front_applies_the_shelf_cap(self):
        c = ctx([line("PARA", 2, 1), line("PARA", 1, 2)])
        self.assertIn("No more than 2", decide(c, shop(c, [rule("PMED")] * 2), route="front")["reason"])
        c = ctx([line("PARA", 2)])
        self.assertEqual(decide(c, shop(c, [rule("PMED")]), route="front"), {"verdict": "allow", "record": None})


class Prescriptions(unittest.TestCase):
    def test_no_prescription_number_is_refused(self):
        c = ctx([line("AMOX", 21)])
        self.assertIn("needs a prescription", decide(c, shop(c, [rule("POM")]))["reason"])

    def test_an_unknown_number_is_refused(self):
        c = ctx([line("AMOX", 21)], details={"Rx Number": "RX9"})
        self.assertIn("No prescription RX9 was found", decide(c, shop(c, [rule("POM")]))["reason"])

    def test_the_paper_reference_finds_the_customers_record(self):
        c = ctx([line("AMOX", 21)], details={"Rx Number": "PAPER-RX1"})
        self.assertEqual(decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21)]))["verdict"], "allow")
        two = [rx("RX1", "AMOX", 21), dict(rx("RX2", "AMOX", 21), reference="PAPER-RX1")]
        self.assertIn("more than one record", decide(c, shop(c, [rule("POM")], two))["reason"])
        others = [rx("RX1", "AMOX", 21), dict(rx("RX2", "AMOX", 21, customer="Bob"), reference="PAPER-RX1")]
        self.assertEqual(decide(c, shop(c, [rule("POM")], others))["verdict"], "allow")   # another patient's paper number

    def test_another_patients_prescription_is_refused(self):
        c = ctx([line("AMOX", 21)], details={"Rx Number": "RX1"})
        self.assertIn("is for another patient", decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21, "Bob")]))["reason"])

    def test_the_walk_in_customer_is_refused(self):
        c = ctx([line("AMOX", 21)], details={"Rx Number": "RX1"})
        self.assertIn("walk-in", decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21)], walk_in=True))["reason"])

    def test_a_scheduled_line_in_a_unit_with_no_conversion_is_refused(self):
        c = ctx([dict(line("AMOX", 2), uom="Box")], details={"Rx Number": "RX1"})
        s = shop(c, [rule("POM")], [rx("RX1", "AMOX", 21)])
        s["qty"] = [None]
        self.assertIn("its unit Box has no conversion", decide(c, s)["reason"])

    def test_an_item_not_on_the_prescription_is_refused(self):
        c = ctx([line("AMOX", 21)], details={"Rx Number": "RX1"})
        self.assertIn("not on the prescription", decide(c, shop(c, [rule("POM")], [rx("RX1", "TRAM", 10)]))["reason"])

    def test_validity_is_the_classes_from_the_date_written_and_its_last_day_sells(self):
        c = ctx([line("TRAM", 10)], details={"Rx Number": "RX1"})
        last = (TODAY - datetime.timedelta(days=29)).isoformat()      # 30 days: the written day is day 1, today day 30
        self.assertEqual(decide(c, shop(c, [rule("CD2", "POM")], [rx("RX1", "TRAM", 10, written=last)]))["verdict"], "allow")
        late = (TODAY - datetime.timedelta(days=30)).isoformat()
        out = decide(c, shop(c, [rule("CD2", "POM")], [rx("RX1", "TRAM", 10, written=late)]))
        self.assertEqual(out["reason"], "Line 1: TRAM: Prescription RX1 was valid until 2026-10-21.")

    def test_a_prescription_dated_after_today_is_refused(self):
        c = ctx([line("AMOX", 21)], details={"Rx Number": "RX1"})
        out = decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21, written="2026-10-23")]))
        self.assertIn("is dated 2026-10-23, after today", out["reason"])

    def test_occasions_are_counted_however_small_each_dispensing(self):
        sch = R.schedules_of([sched("NG", needs_prescription=1, max_occasions=3)])
        r = R.strictest([sch["NG"]])
        c = ctx([line("A", 1)], details={"Rx Number": "RX1"})
        three = [disp(f"k~{n}", [{"item": "A", "qty": 1, "rx": "RX1"}], R.DISPENSED, seq=n) for n in (1, 2, 3)]
        self.assertIn("nothing left", decide(c, shop(c, [r], [rx("RX1", "A", 10, fills=5)], three))["reason"])
        self.assertEqual(decide(c, shop(c, [r], [rx("RX1", "A", 10, fills=5)], three[:2]))["verdict"], "allow")

    def test_one_drug_per_prescription(self):
        sch = R.schedules_of([sched("SA", needs_prescription=1, one_drug_per_rx=1)])
        two = dict(rx("RX1", "A", 1), items=[{"item": "A", "qty": 1, "directions": ""}, {"item": "B", "qty": 1, "directions": ""}])
        c = ctx([line("A", 1)], details={"Rx Number": "RX1"})
        self.assertIn("names more than one drug", decide(c, shop(c, [R.strictest([sch["SA"]])], [two]))["reason"])

    def test_a_cancelled_prescription_is_refused(self):
        c = ctx([line("AMOX", 21)], details={"Rx Number": "RX1"})
        self.assertIn("is cancelled", decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21, active=False)]))["reason"])

    def test_refills_are_spent_by_counted_dispensings(self):
        c = ctx([line("AMOX", 21)], details={"Rx Number": "RX1"})
        one = disp("Ann~0001", [{"item": "AMOX", "qty": 21, "rx": "RX1"}], R.DISPENSED)
        self.assertEqual(decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21, fills=2)], [one]))["verdict"], "allow")
        two = disp("Ann~0002", [{"item": "AMOX", "qty": 21, "rx": "RX1"}], R.RESERVED, seq=2, sale_ref="other")
        out = decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21, fills=2)], [one, two]))
        self.assertIn("nothing left to dispense", out["reason"])

    def test_a_released_dispensing_gives_its_fill_back(self):
        c = ctx([line("AMOX", 21)], details={"Rx Number": "RX1"})
        gone = disp("Ann~0001", [{"item": "AMOX", "qty": 21, "rx": "RX1"}], R.RELEASED)
        self.assertEqual(decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21)], [gone]))["verdict"], "allow")

    def test_this_sales_own_earlier_reservation_is_not_counted_twice(self):
        c = ctx([line("AMOX", 21)], details={"Rx Number": "RX1"}, sale_ref="s1")
        mine = disp("Ann~0001", [{"item": "AMOX", "qty": 21, "rx": "RX1"}], R.RESERVED, sale_ref="s1")
        self.assertEqual(decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21)], [mine]))["verdict"], "allow")

    def test_partial_dispensing_leaves_the_rest_and_a_line_over_the_rest_is_refused(self):
        c = ctx([line("AMOX", 20)], details={"Rx Number": "RX1"})
        part = disp("Ann~0001", [{"item": "AMOX", "qty": 10, "rx": "RX1"}], R.DISPENSED)
        out = decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 30)], [part]))
        self.assertEqual(out["verdict"], "allow")
        c = ctx([line("AMOX", 21)], details={"Rx Number": "RX1"})
        out = decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 30)], [part]))
        self.assertIn("has only 20 of this left", out["reason"])

    def test_a_sale_dispenses_at_most_one_fill(self):
        c = ctx([line("AMOX", 42)], details={"Rx Number": "RX1"})
        self.assertIn("has only 21", decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21, fills=3)]))["reason"])

    def test_the_schedule_caps_the_fills_a_prescription_authorises(self):
        c = ctx([line("TRAM", 10)], details={"Rx Number": "RX1"})
        one = disp("Ann~0001", [{"item": "TRAM", "qty": 10, "rx": "RX1"}], R.DISPENSED)
        out = decide(c, shop(c, [rule("CD2", "POM")], [rx("RX1", "TRAM", 10, fills=3)], [one]))
        self.assertIn("nothing left", out["reason"])

    def test_a_retained_prescription_dispenses_once_even_partly(self):
        c = ctx([line("AMOX", 5)], details={"Rx Number": "RX1"})
        part = disp("Ann~0001", [{"item": "AMOX", "qty": 5, "rx": "RX1"}], R.DISPENSED)
        out = decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21, fills=3, retained=True)], [part]))
        self.assertIn("nothing left", out["reason"])

    def test_a_prescription_changed_after_its_first_dispense_is_refused(self):
        c = ctx([line("AMOX", 21)], details={"Rx Number": "RX1"})
        before = rx("RX1", "AMOX", 21, fills=2)
        first = disp("Ann~0001", [{"item": "AMOX", "qty": 21, "rx": "RX1"}], R.DISPENSED, fp={"RX1": R.fingerprint(before)})
        self.assertEqual(decide(c, shop(c, [rule("POM")], [before], [first]))["verdict"], "allow")
        edited = rx("RX1", "AMOX", 21, fills=5)
        self.assertIn("was changed after it was dispensed", decide(c, shop(c, [rule("POM")], [edited], [first]))["reason"])

    def test_an_allowed_sale_records_its_lines_and_the_fingerprint(self):
        c = ctx([line("AMOX", 21)], details={"Rx Number": "RX1"})
        p = rx("RX1", "AMOX", 21)
        out = decide(c, shop(c, [rule("POM")], [p]))
        self.assertEqual(out["record"], {"lines": [{"item": "AMOX", "qty": 21, "rx": "RX1", "schedules": ["POM"]}],
                                         "fingerprints": {"RX1": R.fingerprint(p)}, "prescriber": "Dr Who",
                                         "directions": ""})

    def test_a_register_item_not_on_the_prescription_goes_in_a_sale_of_its_own(self):
        c = ctx([line("AMOX", 21, 1), line("POISON", 1, 2)], details={"Rx Number": "RX1"})
        out = decide(c, shop(c, [rule("POM"), rule("KEP1")], [rx("RX1", "AMOX", 21)]))
        self.assertEqual(out["reason"], "Line 2: POISON: Sell this in a sale of its own: it is not on the prescription this sale names.")
        c = ctx([line("POISON", 1)])                                    # on its own, with no prescription: allowed
        self.assertEqual(decide(c, shop(c, [rule("KEP1")]))["verdict"], "allow")
        c = ctx([line("POISON", 1)], details={"Rx Number": "RX2"})       # on the prescription: allowed
        self.assertEqual(decide(c, shop(c, [rule("KEP1")], [rx("RX2", "POISON", 1)]))["verdict"], "allow")

    def test_several_numbers_in_one_detail(self):
        self.assertEqual(R.refs_of(" RX1, RX2;RX3 ,RX4,RX5,RX6"), ["RX1", "RX2", "RX3", "RX4", "RX5"])
        self.assertEqual(R.refs_of("KNH 12345"), ["KNH 12345"])        # a paper number may hold a space
        c = ctx([line("AMOX", 21, 1), line("TRAM", 10, 2)], details={"Rx Number": "RX1, RX2"})
        out = decide(c, shop(c, [rule("POM"), rule("CD2", "POM")], [rx("RX1", "AMOX", 21), rx("RX2", "TRAM", 10)]))
        self.assertEqual(out["verdict"], "allow")
        self.assertEqual(sorted(x["rx"] for x in out["record"]["lines"]), ["RX1", "RX2"])


class RxDate(unittest.TestCase):
    """0.1.3: the date the prescription was written, on the sale for a register that books it (K1-d)."""
    def desk(self, rules, rxs, details=None, lines=None):
        c = ctx(lines or [line("AMOX", 21)], details=dict({"Rx Number": ",".join(r["name"] for r in rxs)}, **(details or {})),
                source="desk")
        return decide(c, shop(c, rules, rxs))

    def till(self, rules, rxs, details=None, lines=None):
        c = ctx(lines or [line("AMOX", 21)], details=dict({"Rx Number": ",".join(r["name"] for r in rxs)}, **(details or {})))
        return decide(c, shop(c, rules, rxs))

    def test_the_desk_is_filled_with_the_prescriptions_date_over_whatever_was_typed(self):
        p = rx("RX1", "AMOX", 21, written="2026-10-19")
        for typed in ("", "2026-01-01"):
            out = self.desk([rule("POM")], [p], {"Rx Date": typed})
            self.assertEqual((out["verdict"], out["fields"]), ("fill", {"pp_rxc_rx_date": "2026-10-19"}), typed)
            self.assertTrue(out["record"])                    # a fill reserves as an allow does

    def test_a_linked_desk_line_is_filled_too_and_the_field_takes_the_prefix(self):
        c = dict(ctx([line("AMOX", 21, linked=True)], source="desk"), details={"ACME RXC Rx Number": "RX1"})
        out = R.decide(c, "desk", shop(c, [rule("POM")], [rx("RX1", "AMOX", 21, written="2026-10-19")]), TODAY, "ACME RXC")
        self.assertEqual((out["verdict"], out["fields"], out["record"]), ("fill", {"acme_rxc_rx_date": "2026-10-19"}, None))

    def test_the_till_refuses_a_date_that_is_not_the_prescriptions(self):
        out = self.till([rule("POM")], [rx("RX1", "AMOX", 21, written="2026-10-19")], {"Rx Date": "19/10/2026"})
        self.assertEqual(out["reason"], "Line 1: AMOX: Prescription RX1 was written on 2026-10-19. Correct the date in "
                                        "Sale details.")

    def test_the_till_takes_the_right_date_and_an_empty_one_unless_the_schedule_books_it(self):
        p = rx("RX1", "AMOX", 21, written="2026-10-19")
        self.assertEqual(self.till([rule("POM")], [p], {"Rx Date": "2026-10-19"})["verdict"], "allow")
        self.assertEqual(self.till([rule("POM")], [p])["verdict"], "allow")
        self.assertEqual(self.till([rule("DATED")], [p])["reason"],
                         "Line 1: AMOX: needs the prescription's date in Sale details: 2026-10-19.")
        self.assertEqual(self.till([rule("DATED")], [p], {"Rx Date": "2026-10-19"})["verdict"], "allow")

    def test_prescriptions_of_two_days_are_refused_where_a_date_is_booked_or_typed(self):
        ps = [rx("RX1", "AMOX", 21, written="2026-10-19"), rx("RX2", "TRAM", 10, written="2026-10-20")]
        two = [line("AMOX", 21, 1), line("TRAM", 10, 2)]
        words = "Line 1: AMOX: Prescriptions RX1, RX2 were written on different days. Sell each in a sale of its own."
        self.assertEqual(self.till([rule("DATED"), rule("POM")], ps, lines=two)["reason"], words)
        self.assertEqual(self.till([rule("POM"), rule("POM")], ps, {"Rx Date": "2026-10-19"}, lines=two)["reason"], words)
        self.assertEqual(self.desk([rule("DATED"), rule("POM")], ps, lines=two)["reason"], words)
        self.assertEqual(self.till([rule("POM"), rule("POM")], ps, lines=two)["verdict"], "allow")
        self.assertEqual(self.desk([rule("POM"), rule("POM")], ps, lines=two)["verdict"], "allow")    # no date to fill

    def test_a_prescription_with_no_date_never_fills_an_empty_value(self):
        c = ctx([line("AMOX", 21, linked=True)], details={"Rx Number": "RX1"}, source="desk")
        out = decide(c, shop(c, [rule("POM")], [rx("RX1", "AMOX", 21, written="")]))
        self.assertEqual(out["verdict"], "allow")

    def test_the_register_columns_the_dispensing_keeps(self):
        ps = [rx("RX1", "AMOX", 21, directions="1 capsule three times a day"), rx("RX2", "TRAM", 10)]
        ps[1]["prescriber"] = "Dr Two"
        out = self.till([rule("POM"), rule("POM")], ps, {"Directions": "as the sale says"},
                        lines=[line("AMOX", 21, 1), line("TRAM", 10, 2)])
        self.assertEqual((out["record"]["prescriber"], out["record"]["directions"]),
                         ("Dr Who; Dr Two", "AMOX: 1 capsule three times a day; TRAM: as the sale says"))
        c = ctx([line("PARA", 2)])                    # a capped sale with no prescription: no prescriber, no dose
        out = decide(c, shop(c, [R.strictest([dict(SCHEDULES["PMED"], freq=[], freq_qty=10, freq_days=7)])]))
        self.assertEqual((out["record"] or {}).get("prescriber", ""), "")


class Patient(unittest.TestCase):
    def test_a_controlled_sale_needs_the_customers_identity_fields(self):
        c = ctx([line("TRAM", 10)], details={"Rx Number": "RX1"})
        out = decide(c, shop(c, [rule("CD2", "POM")], [rx("RX1", "TRAM", 10)], fields={"id_number": "", "birth_date": "x"}))
        self.assertIn("national or residence ID", out["reason"])
        out = decide(c, shop(c, [rule("CD2", "POM")], [rx("RX1", "TRAM", 10)], fields={"id_number": "1", "birth_date": ""}))
        self.assertIn("date of birth", out["reason"])

    def test_a_walk_in_is_refused_a_schedule_that_needs_a_patient_field(self):
        rules = R.schedules_of([sched("EGP", axis="Prescription", needs_consent=1)])
        c = ctx([line("PARA", 1)])
        out = decide(c, shop(c, [R.strictest([rules["EGP"]])], walk_in=True, fields={}))
        self.assertIn("needs a named customer, not a walk-in sale.", out["reason"])

    def test_every_identity_refusal_fits_the_tills_sentence_whole(self):
        # PH-B1d: the longest field's words, a two-digit line and a 24-character item, still end with where to add it
        for _tick, _field, words in R.IDENTITY:
            out = R._refuse({"n": 12, "item": "X" * 40}, R.ID_REFUSAL.format(words=words))
            self.assertLessEqual(len(out["reason"]), R.TEXT_MAX)
            self.assertTrue(out["reason"].endswith(R.ID_REFUSAL.format(words=words)), words)

    def test_a_schedule_that_needs_consent_waits_for_the_patients_dated_consent(self):
        rules = R.schedules_of([sched("EGP", axis="Prescription", needs_prescription=1, validity_days=30, needs_consent=1)])
        self.assertEqual(rules["EGP"]["ids"], ("consent_date",))
        c = ctx([line("AMOX", 21)], details={"Rx Number": "RX1"})
        r = R.strictest([rules["EGP"]])
        base = shop(c, [rule("POM")], [rx("RX1", "AMOX", 21)], fields={"id_number": "1", "birth_date": "x"})
        out = decide(c, dict(base, rules=[r]))
        self.assertEqual(out["verdict"], "refuse")
        self.assertIn("needs the customer's consent to keep their records. Add it on their patient record on the Desk.", out["reason"])
        ok = decide(c, dict(base, rules=[r], customer_fields={"consent_date": "2026-10-01"}))
        self.assertEqual(ok["verdict"], "allow")
        # a schedule without the tick never asks for it, and the strictest of two keeps it
        self.assertEqual(decide(c, base)["verdict"], "allow")
        self.assertIn("consent_date", R.strictest([rules["EGP"], SCHEDULES["POM"]])["ids"])

    def test_the_quantity_cap_per_sale_adds_the_items_lines(self):
        c = ctx([line("TRAM", 15, 1), line("TRAM", 6, 2)], details={"Rx Number": "RX1"})
        out = decide(c, shop(c, [rule("CD2", "POM")] * 2, [rx("RX1", "TRAM", 30)]))
        self.assertIn("No more than 20", out["reason"])

    def test_two_equal_lines_of_a_capped_item_are_both_recorded(self):
        c = ctx([line("TRAM", 10, 1), line("TRAM", 10, 2)], details={"Rx Number": "RX1"})
        sch = R.schedules_of([sched("F", freq_qty=40, freq_days=30)])
        out = decide(c, shop(c, [R.strictest([sch["F"]])] * 2))
        self.assertEqual([x["qty"] for x in out["record"]["lines"]], [10, 10])

    def test_the_frequency_cap_counts_the_patients_window_and_this_sale(self):
        c = ctx([line("TRAM", 15)], details={"Rx Number": "RX2"})
        old = disp("Ann~0001", [{"item": "TRAM", "qty": 25, "rx": "RX1", "schedules": ["CD2", "POM"]}], R.DISPENSED,
                   day=TODAY - datetime.timedelta(days=10))
        older = disp("Ann~0002", [{"item": "TRAM", "qty": 20, "rx": "RX0", "schedules": ["CD2", "POM"]}], R.DISPENSED,
                     seq=2, day=TODAY - datetime.timedelta(days=30))
        out = decide(c, shop(c, [rule("CD2", "POM")], [rx("RX2", "TRAM", 20)], [old, older]))
        self.assertEqual(out["verdict"], "allow")        # 25 in the window + 15 = 40 ≤ 40; the 30-day-old one is outside
        c = ctx([line("TRAM", 16)], details={"Rx Number": "RX2"})
        out = decide(c, shop(c, [rule("CD2", "POM")], [rx("RX2", "TRAM", 20)], [old, older]))
        self.assertIn("reached the limit for CD2 until 2026-11-11", out["reason"])

    def test_directions_and_a_doctor_per_group_from_the_details_the_prescription_or_the_item(self):
        c = ctx([line("SYRUP", 1)])
        items = {"SYRUP": {"template": "", "stock_uom": "Nos", "directions": ""}}
        self.assertIn("doctor's name", decide(c, shop(c, [None], directions=[True], items=items))["reason"])
        c = ctx([line("SYRUP", 1)], details={"Prescriber": "Dr A"})
        self.assertIn("directions for use", decide(c, shop(c, [None], directions=[True], items=items))["reason"])
        items["SYRUP"]["directions"] = "5 ml twice a day"
        self.assertEqual(decide(c, shop(c, [None], directions=[True], items=items))["verdict"], "allow")


class Returns(unittest.TestCase):
    def test_dispensed_medicine_is_not_taken_back(self):
        c = ctx([line("AMOX", -21)], stage="return")
        self.assertIn("Dispensed medicine cannot be taken back.", decide(c, shop(c, [rule("POM")]))["reason"])

    def test_an_exchanges_returned_line_is_judged_too(self):
        c = ctx([line("BREAD", 1, 1), line("AMOX", -21, 2)])
        self.assertIn("cannot be taken back", decide(c, shop(c, [None, rule("POM")]))["reason"])

    def test_a_returnable_medicines_return_gives_back_what_its_dispensing_took(self):
        c = ctx([line("PARA", -2)], stage="return")
        took = disp("Ann~0001", [{"item": "PARA", "qty": 2, "rx": "", "schedules": ["PMED"]}], R.DISPENSED)
        out = decide(c, shop(c, [rule("PMED")], returned_from=[took]))
        self.assertEqual(out["record"]["lines"], [{"item": "PARA", "qty": -2, "rx": "", "schedules": ["PMED"], "from": "Ann~0001"}])

    def test_a_quantity_is_given_back_once_and_only_by_a_return_that_moves_stock(self):
        took = disp("Ann~0001", [{"item": "PARA", "qty": 2, "rx": "", "schedules": ["PMED"]}], R.DISPENSED)
        back = disp("Ann~0002", [{"item": "PARA", "qty": -2, "rx": "", "schedules": ["PMED"], "from": "Ann~0001"}],
                    R.RETURNED, seq=2, sale_ref="ret-1")
        c = ctx([line("PARA", -2)], stage="return", sale_ref="ret-2")
        self.assertIsNone(decide(c, shop(c, [rule("PMED")], dispensings=[took, back], returned_from=[took]))["record"])
        c = dict(ctx([line("PARA", -2)], stage="return", source="desk"), moves_stock=False)   # a money-only credit note
        self.assertIsNone(decide(c, shop(c, [rule("PMED")], returned_from=[took]), route="desk")["record"])

    def test_no_give_back_where_a_schedule_says_so(self):
        c = ctx([line("X", -2)], stage="return")
        took = disp("Ann~0001", [{"item": "X", "qty": 2, "rx": "R", "schedules": ["GHA", "GH1019"]}], R.DISPENSED)
        self.assertIsNone(decide(c, shop(c, [rule("GHA", "GH1019")], returned_from=[took]))["record"])

    def test_a_desk_line_from_a_linked_parent_is_not_checked_but_its_return_is(self):
        c = ctx([line("AMOX", 21, linked=True)], source="desk")
        self.assertEqual(decide(c, shop(c, [rule("POM")], pharmacist=None), route="desk"), {"verdict": "allow", "record": None})
        c = ctx([line("AMOX", -21, linked=True)], source="desk", stage="return")
        self.assertIn("cannot be taken back", decide(c, shop(c, [rule("POM")]), route="desk")["reason"])


class Counting(unittest.TestCase):
    STATES = {"sales": {"s-booked": ("INV-1", 1), "s-cancelled": ("INV-2", 2)}, "returns": {"r-booked": ("INV-3", 1)},
              "closed_days": {"DAY-0"}, "documents": {"Sales Order:SO-1": 1, "Sales Order:SO-2": 2}}

    def resolve(self, **k):
        d = disp("Ann~0001", [{"item": "A", "qty": k.pop("qty", 1)}], k.pop("status", R.RESERVED))
        d.update(k)
        return R.resolve(d, self.STATES)

    def test_a_booked_sale_is_dispensed_a_cancelled_one_released(self):
        self.assertEqual(self.resolve(sale_ref=" S-Booked "), R.DISPENSED)     # the till stores it stripped, lower-cased
        self.assertEqual(self.resolve(sale_ref="s-cancelled", status=R.DISPENSED), R.RELEASED)

    def test_an_unbooked_sale_holds_until_its_day_closes_never_on_a_timer(self):
        self.assertEqual(self.resolve(sale_ref="s-new", pos_opening="DAY-9"), R.RESERVED)
        self.assertEqual(self.resolve(sale_ref="s-new", pos_opening="DAY-0"), R.RELEASED)

    def test_a_give_back_counts_only_once_its_return_is_booked(self):
        self.assertEqual(self.resolve(sale_ref="r-booked", qty=-1), R.RETURNED)
        self.assertEqual(self.resolve(sale_ref="r-new", qty=-1, pos_opening="DAY-9"), R.RESERVED)
        d = disp("x", [{"item": "A", "qty": -1}], R.RESERVED)
        self.assertFalse(R.counts(d))
        self.assertTrue(R.counts(dict(d, status=R.RETURNED)))

    def test_a_desk_document_the_shop_hides_is_never_read_as_gone(self):
        states = dict(self.STATES, documents={"Sales Order:SO-9": ("hidden", None), "Sales Order:SO-8": (1, "Bob")})
        d = disp("k~1", [{"item": "A", "qty": 1}], R.RESERVED)
        self.assertEqual(R.resolve(dict(d, source="desk", sale_ref="Sales Order:SO-9"), states), R.RESERVED)
        # its name taken by another customer's document: the original was never submitted
        self.assertEqual(R.resolve(dict(d, source="desk", sale_ref="Sales Order:SO-8", customer="Ann"), states), R.RELEASED)

    def test_a_status_set_by_hand_never_outlives_what_the_shop_shows(self):
        d = disp("k~2", [{"item": "A", "qty": 1}], R.RELEASED, seq=2, sale_ref="s-booked")
        states = dict(self.STATES, newest={"s-booked": "k~2"})
        self.assertEqual(R.resolve(d, states), R.DISPENSED)          # released by hand, but its sale is booked
        unbooked = disp("k~3", [{"item": "A", "qty": 1}], R.RELEASED, seq=3, sale_ref="s-new")
        self.assertEqual(R.resolve(unbooked, dict(states, newest={"s-new": "k~3"})), R.RELEASED)   # the stuck one stays released

    def test_only_the_newest_dispensing_of_a_sale_is_its_booking(self):
        old = disp("k~1", [{"item": "A", "qty": 1}], R.RESERVED, seq=1, sale_ref="s-booked")
        self.assertEqual(R.resolve(old, dict(self.STATES, newest={"s-booked": "k~2"})), R.RELEASED)

    def test_a_desk_dispensing_follows_its_document(self):
        self.assertEqual(self.resolve(source="desk", sale_ref="Sales Order:SO-1"), R.DISPENSED)
        self.assertEqual(self.resolve(source="desk", sale_ref="Sales Order:SO-2"), R.RELEASED)    # cancelled
        self.assertEqual(self.resolve(source="desk", sale_ref="Sales Order:SO-3"), R.RELEASED)    # deleted

    def test_the_next_number_and_the_same_record(self):
        ds = [disp("Ann~0001", [], seq=1), disp("Ann~0007", [], seq=7)]
        key = R.patient_key("Ann")
        self.assertEqual(R.next_name("Ann", ds), (f"{key}~0008", 8))
        self.assertEqual(R.next_name("Ann", []), (f"{key}~0001", 1))
        self.assertNotIn("Ann", key)                       # the patient's name is never in a record's name
        self.assertNotEqual(key, R.patient_key("Bob"))
        d = disp("Ann~0001", [{"item": "A", "qty": 2, "rx": "R"}])
        self.assertTrue(R.same_record(d, {"lines": [{"item": "A", "qty": 2.0, "rx": "R", "schedules": []}]}))
        self.assertFalse(R.same_record(d, {"lines": [{"item": "A", "qty": 3, "rx": "R"}]}))

    def test_a_dispensings_lines_are_read_from_its_json(self):
        rec = {"name": "Ann~0001", "seq": 1, "status": "Dispensed", "day": "2026-10-20",
               "lines_json": json.dumps({"lines": [{"item": "A", "qty": 2, "rx": "R"}], "fingerprints": {"R": "f"}})}
        (d,) = R.dispensings_of([rec])
        self.assertEqual((d["lines"][0]["qty"], d["fingerprints"], d["day"]), (2, {"R": "f"}, datetime.date(2026, 10, 20)))


class Shapes(unittest.TestCase):
    def body(self, **k):
        c = {"v": 1, "stage": "sale", "sale_ref": "S1", "operator": "ph@shop", "customer": "Ann", "pos_profile": "D",
             "pos_opening": "DAY", "sale_attributes": [{"name": f"{P} Rx Number", "value": " RX1 "}],
             "lines": [{"line_no": 1, "item_code": "AMOX", "item_group": "Rx", "qty_milli": 21000, "uom": "Nos"}]}
        c.update(k)
        return {"point": "check/1", "context": c}

    def test_a_till_check_reads_quantities_in_units_and_details_by_name(self):
        c = R.sale_context(self.body())
        self.assertEqual((c["lines"][0]["qty"], c["details"][f"{P} Rx Number"]), (21, "RX1"))

    def test_a_malformed_check_is_refused(self):
        for bad in ({"point": "check/2"}, self.body(lines=[{"item_code": "A"}]), self.body(stage="later"),
                    self.body(sale_attributes=[{"name": 1}]), self.body(return_of="INV")):
            with self.assertRaises(ValueError):
                R.sale_context(bad)

    def test_a_desk_check_reads_stock_qty_parents_and_the_apps_fields(self):
        body = {"point": "doccheck/1", "context": {"v": 1, "event": "submit", "doctype": "Delivery Note", "name": "DN-1",
                "user": "clerk@shop", "fields": {"customer": "Ann", "is_return": 0, "pp_rxc_rx_number": "RX1",
                                                 "items": [{"item_code": "AMOX", "item_group": "Rx", "stock_qty": 21000,
                                                            "against_sales_order": "SO-1", "so_detail": "row-1"}]}}}
        c = R.desk_context(body, P)
        self.assertEqual((c["sale_ref"], c["lines"][0]["qty"], c["lines"][0]["linked"], c["details"][f"{P} Rx Number"]),
                         ("Delivery Note:DN-1", 21, True, "RX1"))
        body["context"]["fields"]["items"][0].update(against_sales_order="", so_detail="", against_sales_invoice="SI-1",
                                                     si_detail="row-9")                 # a delivery made from an invoice
        self.assertTrue(R.desk_context(body, P)["lines"][0]["linked"])
        body["context"]["fields"]["items"][0].update(against_sales_order="SO-1", so_detail="", si_detail="",
                                                     against_sales_invoice="")
        body["context"]["fields"]["items"][0]["so_detail"] = ""     # a parent's name typed on a line, no row: not linked
        self.assertFalse(R.desk_context(body, P)["lines"][0]["linked"])
        body["context"]["doctype"] = "Purchase Order"
        with self.assertRaises(ValueError):
            R.desk_context(body, P)

    def test_a_till_check_with_no_sale_reference_is_not_judged(self):
        with self.assertRaises(ValueError):
            R.sale_context(self.body(sale_ref=""))


if __name__ == "__main__":
    unittest.main()
