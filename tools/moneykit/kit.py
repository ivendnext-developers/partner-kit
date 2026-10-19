# kit.py — the money test kit, IN THE SHOP'S CONSOLE as Administrator, on a STAGING shop (it books sales and closes days).
#
# For every basket: PREVIEW it with the till's own recompute, BOOK it with the till's own submit_tender (simulated
# card, as the cashier), and compare the grand total, the tax and every line amount, preview against the booked
# invoice. Any difference — or a booking refused that the baseline booked — is a RED row. Every POS day the kit opens
# is closed (till.day). Steps: seed · stock · samples:<s1>:<s2> · run:<label> · expect_line:<item>:<net>[:<list>] ·
# expect_detail:<attribute>:<value> · expect_refused:<basket id>:<words> · expect_batch:<item>:<batch> ·
# expect_line_value:<item>:<attribute>:<value> · gate_stock:<file> · gate:<file> · pos_day_check.
#
# SETTINGS — each is a step too, given before the others (a console that runs this file's TEXT gives it no __file__, and
# environment variables may not reach the console). Nothing in this file names a particular shop:
#   kit_dir:<folder>   where kit.py, till.py, baskets.py and printcheck.py sit in the bench (default: this file's folder,
#                      when the console runs it as a file)
#   shop:<file>        the cashier, enrolled device, POS profile and terminal the kit rings with (default: shop.json beside
#                      till.py; shape: shop.example.json)
#   record:<file>      where the run's record is written (default: pp_out.json in the console user's home)
#   baseline:<file>    where the baseline run keeps what it booked, for the later runs (default: pp_kit_baseline.json there)
#   golden:<file>      a golden baskets file (baskets.py) — optional: without it a run rings no golden baskets, and says so
#   seeder:<file>      a promotions seeder (seed, verify, activate, deactivate, restore) — optional: without it there is no
#                      seed step and no promotion basket
#   recorded:<file>    your recorded baskets with their answers (the shape of samples/s12_release_gate/baskets.json) — optional
# The release gate (samples/s12_release_gate/release_gate.sh) calls only gate_stock, gate and pos_day_check.
# Precedent read first: ivendnext/iVendNext_PWA · apps/ivendnext_mpos/ivendnext_mpos/tests/test_preview_book_divergence.py
# @ 05bb4dab (preview figure vs booked figure on the same cart, through submit_tender).
import contextlib
import io
import json
import os
import sys

import frappe
from frappe.utils import flt

B = till = None           # baskets.py and till.py, imported from kit_dir by the first step that is not a setting
OUT = {"ok": False}
CFG = {"kit_dir": os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else None,
       "shop": None, "record": os.path.expanduser("~/pp_out.json"), "baseline": os.path.expanduser("~/pp_kit_baseline.json"),
       "golden": None, "seeder": None, "recorded": None}
SETTINGS = set(CFG)
TOL = 0.005
DAY_MAX = 40
SEED_NS = {}
EXTRA = [None]            # set by the step extra:<file> — a sample's OWN baskets, rung in addition (S7's synthetic items)
PRINT_FORMAT = [None]     # set by the step print_format:<name> — then every booked sale is also PRINTED and read back (S4)


def _setting(key):
    def step(value):
        if till is not None and key in ("kit_dir", "shop"):   # the kit is already loaded and pointed at a shop
            raise RuntimeError(f"the setting {key}: comes before the first other step, never after it")
        CFG[key] = value
        say(f"{key}: {value}")
    step.__name__ = key
    return step


for _k in SETTINGS:
    globals()[_k] = _setting(_k)


def _load():
    """Import the kit's own modules from kit_dir, and point till.py at the shop (once, before the first real step)."""
    global B, till
    if till is not None:
        return
    if not CFG["kit_dir"] or not os.path.isfile(os.path.join(CFG["kit_dir"], "till.py")):
        raise RuntimeError(f"the kit's folder is not known or holds no till.py ({CFG['kit_dir']!r}): give the step kit_dir:<folder>")
    sys.path[:0] = [CFG["kit_dir"]]
    import baskets as _b
    import till as _t
    B, till = _b, _t
    if CFG["shop"]:
        till.configure_from(CFG["shop"])
    till.need("PERSONA"), till.need("DEVICE"), till.need("PROFILE"), till.need("TERMINAL")   # fail here, before a day opens
    OUT["settings"] = {**CFG, "shop_values": till.shop(), "shop_from": till.SHOP_FROM}


def say(msg):
    print(f"[pp-kit] {msg}", flush=True)


def _seeder():
    if not CFG["seeder"]:
        raise RuntimeError("no promotions seeder was given: the step seeder:<file> (seed needs one; a run without one rings no offer)")
    if not SEED_NS:
        exec(open(CFG["seeder"]).read(), SEED_NS, SEED_NS)
    return SEED_NS


def _quiet(fn, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = fn(*a, **k)
    return out, buf.getvalue()


def seed():
    """The promotions seed (the seeder named by the step seeder:<file>): every UC fixture inserted INACTIVE."""
    ns = _seeder()
    _, log = _quiet(ns["seed"])
    gaps, vlog = _quiet(ns["verify"])
    OUT["seed"] = {"log": log.splitlines(), "verify_gaps": gaps, "verify": vlog.splitlines(),
                   "seeded": sorted(frappe.get_all("Promotion Bonus Buys Master",
                                                   filters={"name": ["like", "UC-%"]}, pluck="name"))}
    say(f"seed: {len(OUT['seed']['seeded'])} UC masters; verify gaps {gaps}")


def stock():
    """Top up every item the basket set uses at the till's store, so a whole run cannot run out (Material Receipt)."""
    _top_up(_basket_set()["baskets"])


def _top_up(baskets):
    wh = frappe.db.get_value("POS Profile", till.PROFILE, "warehouse")
    company = frappe.db.get_value("POS Profile", till.PROFILE, "company")
    rows = []
    for code, need in B.items_used(baskets).items():
        have = flt(frappe.db.get_value("Bin", {"item_code": code, "warehouse": wh}, "actual_qty"))
        want = need * 2 + 20     # one run's need, twice over; topped up before EVERY run (review fold)
        if have < want:
            rate = flt(frappe.db.get_value("Item", code, "valuation_rate")) or flt(
                frappe.db.get_value("Item Price", {"item_code": code, "selling": 1}, "price_list_rate")) * 0.6
            rows.append({"item_code": code, "qty": want - have, "t_warehouse": wh, "basic_rate": rate})
    if rows:
        se = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt", "company": company,
                             "items": rows, "remarks": "Partner Programme money kit: stock top-up"})
        se.insert(ignore_permissions=True)
        se.submit()
        frappe.db.commit()
        OUT["stock"] = {"entry": se.name, "rows": [(r["item_code"], r["qty"]) for r in rows]}
    else:
        OUT["stock"] = {"entry": None}
    say(f"stock: {OUT['stock']}")


def print_format(name):
    """From now on each booked sale is rendered through this print format and the printed grand total and tax must be
    the booked figures (a format prints money, it never computes it). The receipt pack, S4."""
    PRINT_FORMAT[0] = name
    say(f"print_format: {name}")


def _printed_agrees(inv) -> list[str]:
    import printcheck
    return printcheck.agrees(inv, frappe.get_print("POS Invoice", inv.name, print_format=PRINT_FORMAT[0]))


def samples(s1, s2):
    """S1's and S2's webhooks on or off (they ARE those samples' server side; their till keys are the hosted apps,
    installed or uninstalled by our bench runner). Matched by the services' ports: S1 :8121, S2 :8123."""
    state = {}
    for name, url, on in frappe.get_all("Webhook", fields=["name", "request_url", "enabled"], as_list=True):
        port = ":8121/" if ":8121/" in (url or "") else ":8123/" if ":8123/" in (url or "") else None
        if port:
            want = int(s1) if port == ":8121/" else int(s2)
            frappe.db.set_value("Webhook", name, "enabled", want)
            state[name] = want
    # ⚠ the framework fires webhooks from a CACHED list (`frappe.cache "webhooks"`, cleared only by a Webhook's own
    # save). A raw set_value leaves the old list live, so each run fired the PREVIOUS run's webhooks — measured on our test bench
    # by attributing deliveries to each run's own invoices. Clear it.
    frappe.cache.delete_value("webhooks")
    frappe.db.commit()
    OUT["webhooks"] = state
    say(f"samples: {state}")


def _basket_set():
    golden = json.load(open(CFG["golden"])) if CFG["golden"] else {"fixtures": []}   # a file given but missing fails here
    seeded = set(frappe.get_all("Promotion Bonus Buys Master", filters={"name": ["like", "UC-%"]},
                                pluck="name")) if CFG["seeder"] else set()             # no seeder: no offer is switched on
    recorded = json.load(open(CFG["recorded"])) if CFG["recorded"] else None
    bs = B.basket_set(golden, seeded, recorded)
    bs["counts"].update(golden_file=CFG["golden"], seeder=CFG["seeder"], recorded_file=CFG["recorded"])
    if EXTRA[0]:       # a sample's own baskets (ids X001…): rung in every run that names the file, against no baseline
        for i, r in enumerate(json.load(open(EXTRA[0]))["kit_baskets"]):
            bs["baskets"].append({"id": f"X{i + 1:03d}", "source": "extra", "name": r["name"], "promo": None,
                                  "lines": r["lines"], "sale_discount": r.get("sale_discount"),
                                  "sale_attributes": r.get("sale_attributes"),   # sale details, as the till's sheet sends them
                                  # row SET5: the sale's customer, and per line what the till's scan put on it (a batch,
                                  # a line value) — given in the lines' order
                                  "customer": r.get("customer"), "line_extras": r.get("line_extras")})
        bs["counts"]["extra"] = len(json.load(open(EXTRA[0]))["kit_baskets"])
    return bs


def extra(path):
    """From now on the run also rings the baskets under ``kit_baskets`` in this file (items the sample created)."""
    EXTRA[0] = path
    say(f"extra baskets from {path}")


def _by_item(pairs):
    out = {}
    for code, amount in pairs:
        out[code] = round(out.get(code, 0) + flt(amount), 4)
    return out


def compare(pv: dict, inv) -> list[str]:
    diffs = []
    for label, a, b in (("grand total", pv.get("grand_total"), inv.grand_total),
                        ("rounded total", pv.get("rounded_total"), inv.rounded_total),
                        ("tax", pv.get("total_taxes_and_charges"), inv.total_taxes_and_charges)):
        if abs(flt(a) - flt(b)) > TOL:
            diffs.append(f"{label}: till showed {flt(a):.2f}, booked {flt(b):.2f}")
    p = _by_item((ln["item_code"], ln["amount"]) for ln in pv.get("lines") or [])
    i = _by_item((it.item_code, it.amount) for it in inv.items)
    for code in sorted(set(p) | set(i)):
        if abs(p.get(code, 0) - i.get(code, 0)) > TOL:
            diffs.append(f"line {code}: till showed {p.get(code, 0):.2f}, booked {i.get(code, 0):.2f}")
    return diffs


def _ring(b: dict) -> dict:
    row = {"id": b["id"], "source": b["source"], "name": b["name"], "promo": b.get("promo")}
    cart = till.cart_of([tuple(ln) for ln in b["lines"]], customer=b.get("customer"), sale_discount=b.get("sale_discount"))
    if b.get("sale_attributes"):
        cart["sale_attributes"] = b["sale_attributes"]
    for line, extras in zip(cart["lines"], b.get("line_extras") or []):
        line.update(extras or {})
    try:
        if b.get("promo"):
            _quiet(_seeder()["activate"], b["promo"])   # the seeder only for an offer basket: the gate's baskets carry none
        try:
            pv = till.preview(cart)
        except Exception as e:  # noqa: BLE001 — a refusal is a result
            frappe.db.rollback()
            row.update(state="refused at preview", detail=str(e)[:300])
            return row
        row["preview"] = {"grand_total": pv.get("grand_total"), "tax": pv.get("total_taxes_and_charges"),
                          "discounted": flt(pv.get("discount_amount")) + flt(pv.get("total_line_discount")) > 0}
        try:
            row["key"] = till.ukey(b["id"])
            res = till.book(cart, [till.sim_card_auth(b["id"])], row["key"])
        except Exception as e:  # noqa: BLE001 — a refusal is a result (Trap 5 may surface as one)
            frappe.db.rollback()
            row.update(state="refused at booking", detail=str(e)[:400])
            return row
        inv = frappe.get_doc("POS Invoice", res["name"])
        diffs = compare(pv, inv)
        if PRINT_FORMAT[0]:
            diffs += _printed_agrees(inv)
        for k, field in (("grand_total", "grand_total"), ("tax", "total_taxes_and_charges")):
            want = (b.get("expect") or {}).get(k)
            if want is not None and abs(flt(want) - flt(inv.get(field))) > TOL:   # a partner's recorded answer
                diffs.append(f"{k}: recorded answer {flt(want):.2f}, booked {flt(inv.get(field)):.2f}")
        row.update(state="diverged" if diffs else "matched", invoice=inv.name, detail=diffs,
                   booked={"grand_total": inv.grand_total, "tax": inv.total_taxes_and_charges})
        return row
    finally:
        if b.get("promo"):
            _quiet(_seeder()["deactivate"], b["promo"])


def _check_merged(rows, base_drift=None):
    """Where the accounts post: each till sale is merged at the day's close into its own back-office invoice on
    this engine (measured on our test bench). The platform itself re-rounds at that merge — measured with NO sample installed: 17 of 64
    sales came out 0.01 apart. So the rule is RELATIVE: each basket's drift (merged − sale, grand total and
    tax) is recorded by the baseline, and in every later run it must equal the baseline's. A sample that changed the
    merged invoice's money moves the drift (review fold R4)."""
    for r in rows:
        if r["state"] != "matched":
            continue
        merged = frappe.db.get_value("POS Invoice", r["invoice"], "consolidated_invoice")
        if not merged:
            r.update(state="diverged", detail=["the sale was not merged into a back-office invoice at the close"])
            continue
        si = frappe.db.get_value("Sales Invoice", merged, ["grand_total", "total_taxes_and_charges"], as_dict=True)
        drift = [round(flt(si.grand_total) - flt(r["booked"]["grand_total"]), 2),
                 round(flt(si.total_taxes_and_charges) - flt(r["booked"]["tax"]), 2)]
        r.update(merged_invoice=merged, merged_drift=drift)
        if base_drift is not None and r["source"] != "extra":     # an extra basket has no baseline: its drift is recorded only
            want = base_drift.get(r["id"])
            if want is None or any(abs(a - b) > TOL for a, b in zip(drift, want)):
                r.update(state="diverged", detail=[f"merged {merged}: drift from the sale {drift} (grand, tax), "
                                                    f"the platform alone gives {want}"])


def run_documents(rows) -> list[str]:
    """This run's own invoices: each sale and the back-office invoice it was merged into."""
    return [r["invoice"] for r in rows if r.get("invoice")] + [r["merged_invoice"] for r in rows
                                                              if r.get("merged_invoice")]


def deliveries_for(docs) -> dict:
    """webhook -> how many deliveries were logged for these documents."""
    out = {}
    for g in frappe.get_all("Webhook Request Log", filters={"reference_document": ["in", docs or ["-"]]},
                            fields=["webhook"], limit_page_length=0):
        out[g.webhook] = out.get(g.webhook, 0) + 1
    return out


def deliveries_after(path):
    """After the fact: the deliveries logged for a finished run's own invoices (read from its record, a file in the bench)."""
    rec = json.load(open(path))
    docs = run_documents(rec["rows"])
    OUT.setdefault("deliveries_after", {})[path] = {"documents": len(docs), "deliveries": deliveries_for(docs)}
    say(f"deliveries_after {path}: {OUT['deliveries_after'][path]}")


# s4 (a manifest print format) and s5 (configuration) install no app: the run must have NO sample app installed
EXPECTED = {"s1": "pp_wrc", "s2": None, "s3": "pp_pda",   # S2 hosts no app
            "trap": "pp_moneytrap", "s4": None, "s5": None, "s7": None, "s8": None,
            # S10 (an assistant over the MCP server), S11 and S14 (a manifest and a service) install no app
            "s10": None, "s11": None, "s14": None, "s17": None,
            # row SET5: S18, S19 and S20 are manifests (S18 and S20 with a partner's service), no app
            "s18": None, "s19": None, "s20": None}
SAMPLE_APPS = {a for a in EXPECTED.values() if a}


def run(label):
    bs = _basket_set()
    baseline = None
    base_drift = None
    if label != "baseline":
        baseline = json.load(open(CFG["baseline"]))
        booked = set(baseline["booked_ids"])
        base_drift = baseline["merged_drift"]
        todo = [b for b in bs["baskets"] if b["id"] in booked or b["source"] == "extra"]
    else:
        todo = bs["baskets"]
    rows = []
    pda0 = frappe.db.count("PP PDA Deviation") if frappe.db.exists("DocType", "PP PDA Deviation") else None
    # ⚠ at most DAY_MAX sales per day: the engine merges a day of 50+ till sales through a background job, which is
    # refused while the site's scheduler is off (this bench) and runs later where it is on — either way the day would
    # not be closed when the kit ends. Measured on our test bench.
    with till.simulated_card():
        for start in range(0, len(todo), DAY_MAX):
            chunk = []
            with till.day(record=OUT):
                for b in todo[start:start + DAY_MAX]:
                    chunk.append(_ring(b))
                    say(f"{label} {b['id']} {chunk[-1]['state']}")
            _check_merged(chunk, base_drift)   # after the close: the back-office invoice each sale was merged into
            rows += chunk
    if CFG["seeder"]:
        _quiet(_seeder()["restore"])
    # proof the installed sample was LIVE during the run, not merely installed: S3's records; S1's/S2's webhook
    # deliveries ATTRIBUTED to this run's own invoices (sales + their merged invoices). Webhooks are delivered by the
    # worker after the sale commits, so wait until the count stops moving (at most 90 s) — counting by time instead
    # lagged one run behind (measured on our test bench)
    import time
    docs = run_documents(rows)
    last, waited, stable = None, 0, 0
    while waited < 120:
        frappe.db.commit()   # a fresh read of what the worker wrote
        now = deliveries_for(docs)
        stable = stable + 1 if now == last else 0
        # stop only when the count has held still for 30 s AND something arrived — or the wait is spent. (The first
        # version stopped on two equal EMPTY reads, before the worker had delivered anything: measured.)
        if (now and stable >= 3) or (not now and waited >= 90):
            break
        last, waited = now, waited + 10
        time.sleep(10)
    activity = {"pp_pda_records_written": (frappe.db.count("PP PDA Deviation") - pda0) if pda0 is not None else None,
                "webhook_deliveries_for_this_runs_invoices": now}
    count = lambda s: sum(1 for r in rows if r["state"] == s)  # noqa: E731
    summary = {"label": label, "installed_apps": frappe.get_installed_apps(), "basket_set": bs["counts"],
               "skipped": bs["skipped"], "rung": len(rows), "matched": count("matched"),
               "diverged": count("diverged"), "refused_at_booking": count("refused at booking"),
               "refused_at_preview": count("refused at preview"),
               "with_a_discount": sum(1 for r in rows if (r.get("preview") or {}).get("discounted")),
               "extra_baskets": {"rung": sum(1 for r in rows if r["source"] == "extra"),
                                 "matched": sum(1 for r in rows if r["source"] == "extra" and r["state"] == "matched")},
               "recorded_baskets": {"rung": sum(1 for r in rows if r["source"] == "recorded"),
                                    "matched_their_answer": sum(1 for r in rows if r["source"] == "recorded"
                                                                and r["state"] == "matched")},
               "sample_activity": activity}
    apps = set(frappe.get_installed_apps())
    wrong = (apps & SAMPLE_APPS) if label == "baseline" else ((apps & SAMPLE_APPS) ^ ({EXPECTED[label]} - {None}))
    if label == "baseline":
        # the baseline DEFINES the set the other runs ring: what the till could book with no sample installed.
        # A basket it refused is recorded with its words, and is not a money result.
        summary["verdict"] = "GREEN" if not summary["diverged"] else "RED"
        json.dump({"booked_ids": [r["id"] for r in rows if r["state"] == "matched"],
                   "merged_drift": {r["id"]: r["merged_drift"] for r in rows if r.get("merged_drift")}},
                  open(CFG["baseline"], "w"))
        summary["platform_merge_drift"] = sorted(
            (r["id"], r["merged_drift"]) for r in rows if r.get("merged_drift") and any(r["merged_drift"]))
    else:
        summary["verdict"] = "GREEN" if summary["matched"] == len(rows) else "RED"
    if not rows:     # nothing rung proves nothing (every setting optional since row KITMONEY): never a green
        summary["verdict"], summary["why_invalid"] = "INVALID", "no basket was rung"
    if wrong:
        # the run did not have exactly its sample installed: its colour proves nothing either way (review fold R3)
        summary["verdict"] = "INVALID"
        summary["why_invalid"] = f"sample apps installed {sorted(apps & SAMPLE_APPS)}, expected " \
                                 f"{[EXPECTED.get(label)] if label != 'baseline' and EXPECTED.get(label) else []}"
    OUT["run"] = summary
    OUT["rows"] = rows
    OUT["red_rows"] = [r for r in rows if r["state"] not in ("matched",)
                       and not (label == "baseline" and r["state"].startswith("refused"))]
    say(f"RUN {label}: {summary['verdict']} — rung {len(rows)}, matched {summary['matched']}, diverged "
        f"{summary['diverged']}, refused at booking {summary['refused_at_booking']}, at preview "
        f"{summary['refused_at_preview']}, with a discount {summary['with_a_discount']}")


def expect_line(item, net, list_price=None):
    """After run: — the proof that a sample's change to ONE item's price or promotion was LIVE while the baskets rang. Every
    line of that item in the run's extra baskets must have been BOOKED at ``net`` a unit (net of any discount) and, when
    given, from ``list_price``; anything else, or no such line, makes the run RED. Ring the item in an extra basket only:
    a basket with a recorded answer or a baseline would move with the change."""
    lines = [x for r in OUT.get("rows") or [] if r["source"] == "extra" and r.get("invoice")
             for x in frappe.get_doc("POS Invoice", r["invoice"]).items if x.item_code == item]
    got = [{"net": round(flt(x.amount) / flt(x.qty), 4), "list": flt(x.price_list_rate), "qty": flt(x.qty)} for x in lines]
    ok = bool(got) and all(abs(g["net"] - flt(net)) <= TOL and (list_price is None or abs(g["list"] - flt(list_price)) <= TOL)
                           for g in got)
    OUT["expect_line"] = {"item": item, "net": flt(net), "list_price": flt(list_price) if list_price else None,
                          "booked": got, "ok": ok}
    if not ok and (OUT.get("run") or {}).get("verdict") == "GREEN":
        OUT["run"]["verdict"] = "RED"
        OUT["run"]["why_red"] = f"{item} was booked at {got}, not {net} a unit" + (f" from {list_price}" if list_price else "")
    say(f"expect_line {item}: {'held' if ok else 'NOT held'} — want {net}" + (f" from {list_price}" if list_price else "")
        + f", booked {got}; verdict now {(OUT.get('run') or {}).get('verdict')}")


def expect_detail(attribute, value):
    """After run: — a sample that puts a sale detail on a till sale (S17's delivery order): every extra basket's booked sale
    must carry ``attribute`` = ``value`` (the till drops a detail whose name it does not know), or the run is RED."""
    got = [[(x.sale_attribute, x.attribute_value) for x in frappe.get_doc("POS Invoice", r["invoice"]).get(
        "custom_pos_invoice_sale_attribute") or []] for r in OUT.get("rows") or [] if r["source"] == "extra" and r.get("invoice")]
    ok = bool(got) and all((attribute, value) in g for g in got)
    OUT["expect_detail"] = {"attribute": attribute, "value": value, "booked": got, "ok": ok}
    if not ok and (OUT.get("run") or {}).get("verdict") == "GREEN":
        OUT["run"]["verdict"] = "RED"
        OUT["run"]["why_red"] = f"the booked sales carry {got}, not {attribute} = {value}"
    say(f"expect_detail {attribute}: {'held' if ok else 'NOT held'} — booked {got}; verdict now {(OUT.get('run') or {}).get('verdict')}")


def _extra_lines(item):
    return [x for r in OUT.get("rows") or [] if r["source"] == "extra" and r.get("invoice")
            for x in frappe.get_doc("POS Invoice", r["invoice"]).items if x.item_code == item]


def _hold(name, ok, why_red, said):
    """An expectation's verdict: a GREEN run whose expectation did not hold turns RED."""
    if not ok and (OUT.get("run") or {}).get("verdict") == "GREEN":
        OUT["run"]["verdict"] = "RED"
        OUT["run"]["why_red"] = why_red
    say(f"{name}: {'held' if ok else 'NOT held'} — {said}; verdict now {(OUT.get('run') or {}).get('verdict')}")


def expect_refused(basket, *words):
    """After run: — a sample whose check before payment refuses one extra basket (S18). That basket (its id, ``X002``) must
    have been refused at the booking, in words that hold ``words``, and must have booked NOTHING — no invoice for its
    attempt; then it is the one row the run may leave unmatched, and every other row must still match. Anything else is
    RED (the refusal is the sample's result, never a money difference)."""
    words = ":".join(words)       # the step splits on ':'; a sentence may carry one
    row = next((r for r in OUT.get("rows") or [] if r["id"] == basket), None)
    booked = frappe.get_all("POS Invoice", filters={"custom_mpos_idempotency_key": row["key"]}, pluck="name") \
        if row and row.get("key") and frappe.get_meta("POS Invoice").has_field("custom_mpos_idempotency_key") else []
    ok = bool(row) and row["state"] == "refused at booking" and words in (row.get("detail") or "") \
        and not row.get("invoice") and not booked
    OUT["expect_refused"] = {"basket": basket, "words": words, "row": row, "booked": booked, "ok": ok}
    run = OUT.get("run") or {}
    others_held = all(v.get("ok") for k, v in OUT.items() if k.startswith("expect_") and k != "expect_refused"
                      and isinstance(v, dict))     # never turn GREEN over an expectation that already failed (review)
    if ok and others_held and run.get("verdict") == "RED" and run.get("matched") == run.get("rung", 0) - 1:
        run["verdict"], run["refused_as_expected"] = "GREEN", basket      # the one unmatched row is the expected refusal
    _hold("expect_refused", ok, f"{basket} was not refused with '{words}' and nothing booked: {row}",
          f"{basket} {row and row['state']}, booked {booked}")


def expect_batch(item, batch):
    """After run: — every booked line of ``item`` in the extra baskets carries ``batch`` (S19: the unit's own batch)."""
    got = [x.batch_no for x in _extra_lines(item)]
    ok = bool(got) and all(b == batch for b in got)
    OUT["expect_batch"] = {"item": item, "batch": batch, "booked": got, "ok": ok}
    _hold("expect_batch", ok, f"{item} was booked in batch {got}, not {batch}", f"want {batch}, booked {got}")


def expect_line_value(item, attribute, *value):
    """After run: — every extra basket's booked sale carries ``attribute`` = ``value`` on its ``item`` line (S19's unit
    code, S20's captured reference): the line attributes the till sent, as booked."""
    value = ":".join(value)
    got = []
    for r in OUT.get("rows") or []:
        if r["source"] != "extra" or not r.get("invoice"):
            continue
        inv = frappe.get_doc("POS Invoice", r["invoice"])
        rows = {x.idx: x.item_code for x in inv.items}
        got.append([(x.transaction_item_attribute, x.attribute_value) for x in inv.get(
            "custom_pos_invoice_transaction_item_attribute") or [] if rows.get(x.row_no_ref) == item])
    ok = bool(got) and all((attribute, value) in g for g in got)
    OUT["expect_line_value"] = {"item": item, "attribute": attribute, "value": value, "booked": got, "ok": ok}
    _hold("expect_line_value", ok, f"the booked {item} lines carry {got}, not {attribute} = {value}", f"booked {got}")


def _gate_baskets(path):
    """A customer's own baskets (the shape of samples/s12_release_gate/baskets.json), numbered G001…: name, lines, optional sale discount, optional
    recorded answer (``expect``: grand_total and tax)."""
    rows = json.load(open(path))["baskets"]
    return [{"id": f"G{i + 1:03d}", "source": "gate", "name": r["name"], "promo": None, "lines": r["lines"],
             "sale_discount": r.get("sale_discount"), "expect": r.get("expect")} for i, r in enumerate(rows)]


def gate_stock(path):
    """Top up the stock the customer's baskets need (the release gate's own, not the shared set's)."""
    _top_up(_gate_baskets(path))


def gate(path):
    """The release gate's money leg (samples/s12_release_gate/): ring the customer's baskets — preview, booking, the back-office invoice
    after the day closes — and fail any basket whose preview and booking differ OR whose booked totals differ from the answer the
    customer recorded. Every day it opens it closes. The record: OUT['gate'], one row per basket."""
    todo = _gate_baskets(path)
    rows = []
    with till.simulated_card():
        for start in range(0, len(todo), DAY_MAX):
            chunk = []
            with till.day(record=OUT):
                for b in todo[start:start + DAY_MAX]:
                    chunk.append(_ring(b))
                    say(f"gate {b['id']} {chunk[-1]['state']}")
            _check_merged(chunk, None)
            rows += chunk
    OUT["gate"] = [{"id": r["id"], "name": r["name"], "state": r["state"], "detail": r.get("detail"),
                    "expect": next((b["expect"] for b in todo if b["id"] == r["id"]), None),
                    "preview": r.get("preview"), "booked": r.get("booked"), "invoice": r.get("invoice")} for r in rows]
    OUT["gate_green"] = bool(rows) and all(r["state"] == "matched" for r in rows)
    say(f"GATE {'GREEN' if OUT['gate_green'] else 'RED'}: {sum(r['state'] == 'matched' for r in rows)} of {len(rows)} baskets matched")


def pos_day_check():
    OUT["open_days"] = till.open_days()
    say(f"pos_day_check: unclosed {OUT['open_days']}")


def main(steps):
    try:
        for s in steps:
            name, *args = s.split(":")
            if name not in SETTINGS:
                _load()
            globals()[name](*args)
        OUT["ok"] = True
    except Exception as e:
        frappe.db.rollback()
        import traceback
        OUT["ok"], OUT["error"], OUT["trace"] = False, repr(e)[:800], traceback.format_exc()[-3000:]
        print(f"[pp-kit] ERROR {e!r}"[:400], flush=True)
    finally:
        frappe.set_user("Administrator")
        try:   # ALWAYS, even when a step failed: a failed close is exactly when a day is left open (review fold R6)
            OUT["open_days"] = till.open_days()
        except Exception as e:  # noqa: BLE001
            OUT["open_days"] = f"could not read: {e!r}"
        json.dump(OUT, open(CFG["record"], "w"), indent=1, default=str)
