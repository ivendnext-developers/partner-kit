#!/usr/bin/env python3
"""S22 — the shop's configuration, over the record API with the ADMINISTRATOR's key (standard library only). The shape is
sample S5's (``samples/s5_config_pack/apply_config.py``): one data file, idempotent, with an undo.

    PP_BASE=https://shop.example PP_KEY=<admin api key> PP_SECRET=<admin api secret> python3 apply_config.py <command>

    prepare     BEFORE the manifest: the role PP LYL Integration, the ONE integration user (that role only, never Workspace
                Manager), and its rights on the shop's records, each with its reason (config.json).
    apply       AFTER the manifest: a customer group per tier, the plans and settings, one promotion per tier that
                excludes every other group (rebuilt on every run), the receipt's check-by-workflow, and the submit right
                taken from every role but the manager's and the service's.
    switch-on   the shop's own switches: the feed registration's user and its record types ticked on, the till key's
                consent.
    switch-off  the same switches off, nothing removed (if a run fails half-way, nothing is left on).
    remove      everything above, in reverse: switches off, permission rows put back FIRST, then every record this
                script made (one a booked document points at is retired or kept, and the line says which).
    diff        what this script made that is still there, and each permission table against its state before.

What it made, and each permission table as it was before, are kept in ``.s22_before.json`` beside this file (not
committed), so ``remove`` removes exactly that. PP_CONFIG=<file> uses another data file.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "service"))
from shop import Duplicate, Shop, ShopError  # noqa: E402

with open(os.environ.get("PP_CONFIG") or os.path.join(HERE, "config.json")) as _fh:
    CONF = json.load(_fh)
BEFORE = os.environ.get("PP_BEFORE") or os.path.join(HERE, ".s22_before.json")
DAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
PM = "ivendnext_mpos.api.v1"     # the shop's Role Permissions Manager calls, by their iVendNext names
RIGHTS = ("select", "read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "import",
          "share", "print", "email")      # select too: remove puts every row back exactly
WF = "PP LYL Receipt Verification"
T = S = None


def say(*a):
    print(" ", *a, flush=True)


class State:
    def __init__(self):
        self.d = {"made": [], "perms": {}, "had_field": {}}
        if os.path.exists(BEFORE):
            with open(BEFORE) as fh:
                self.d = json.load(fh)

    def save(self):
        with open(BEFORE, "w") as fh:
            json.dump(self.d, fh, indent=1)

    def made(self, dt, name):
        if [dt, name] not in self.d["made"]:
            self.d["made"].append([dt, name])
            self.save()


def ensure(dt, name, doc, update=None):
    if T.get(dt, name) is not None:
        if update:
            T.update(dt, name, update)
        say(f"kept     {dt}: {name}")
        return
    try:
        T.insert(dict(doc, doctype=dt))
    except Duplicate:
        return
    S.made(dt, name)
    say(f"created  {dt}: {name}")


def custom_perms(dt):
    rows = T.list("Custom DocPerm", [["parent", "=", dt]], ["name", "role", "permlevel", "if_owner", *RIGHTS])
    return sorted(rows, key=lambda r: (r["role"], r["permlevel"], r["if_owner"]))


def snapshot_perms(dt):
    if dt not in S.d["perms"]:
        S.d["perms"][dt] = custom_perms(dt)       # [] = the table ran on its standard rows
        S.save()


def effective(dt):
    return T.method(f"{PM}.get_role_permissions", {"doctype": dt}) or []


def grant(dt, role, rights, why):
    snapshot_perms(dt)
    if not any(r["role"] == role and int(r["permlevel"]) == 0 for r in effective(dt)):
        T.method(f"{PM}.add_role_permission", {"parent": dt, "role": role, "permlevel": 0})
        if "export" not in rights:     # a new row carries the framework's default export right: off unless listed
            T.method(f"{PM}.update_role_permission", {"doctype": dt, "role": role, "permlevel": 0, "ptype": "export", "value": 0})
    for right in rights:
        T.method(f"{PM}.update_role_permission", {"doctype": dt, "role": role, "permlevel": 0, "ptype": right, "value": 1})
    say(f"granted  {role} on {dt}: {', '.join(rights)} ({why})")


def take_submit(dt, keep):
    snapshot_perms(dt)
    for r in effective(dt):
        if int(r.get("submit") or 0) and r["role"] not in keep:
            T.method(f"{PM}.update_role_permission", {"doctype": dt, "role": r["role"], "permlevel": r["permlevel"], "ptype": "submit",
                                      "value": 0})
            say(f"took     submit on {dt} from {r['role']}")


def prepare():
    u = CONF["integration_user"]
    ensure("Role", u["role"], {"role_name": u["role"], "desk_access": 1}, update={"disabled": 0})   # back on after a remove
    ensure("User", u["email"], {"email": u["email"], "first_name": u["first_name"], "user_type": "System User",
                                # the screen's "Is Desk User" tick (recipes/integration_user.md step 2): the shop refuses
                                # a user that is neither a desk user nor a POS user
                                "custom_is_desk_user": 1, "send_welcome_email": 0, "roles": [{"role": u["role"]}]},
           update={"enabled": 1})
    roles = [r["role"] for r in (T.get("User", u["email"]) or {}).get("roles") or []]
    if roles != [u["role"]]:
        T.update("User", u["email"], {"roles": [{"role": u["role"]}]})
        say(f"took     {sorted(set(roles) - {u['role']})} off the integration user")
    for g in CONF["integration_rights"]:
        grant(g["doctype"], u["role"], g["rights"], g["why"])
    say("now make its API key (User → Generate Keys) and give it to your service only")


def apply():
    for p in CONF["plans"]:
        ensure("Customer Group", p["customer_group"], {"customer_group_name": p["customer_group"],
                                                       "parent_customer_group": "All Customer Groups", "is_group": 0})
    for p in CONF["plans"]:
        ensure("PP LYL Plan", p["plan_name"], dict(p, active=1), update=dict(p, active=1))
    st = CONF["settings"]
    settings = dict(title="Default", default_plan=st["default_plan"], return_days=st["return_days"],
                    tier_window_days=st["tier_window_days"], currency=CONF["currency"],
                    currency_precision=CONF["currency_precision"], walk_in_customers="\n".join(st["walk_in_customers"]),
                    max_redemption_percent=st.get("max_redemption_percent", 0), earn_on_redemption=st.get("earn_on_redemption", 0))
    # Member cash's payment method is made by the payments app when the wallet goes live: name it once it exists
    if st.get("wallet_mode_of_payment") and T.list("Mode of Payment", [["name", "=", st["wallet_mode_of_payment"]]], ["name"]):
        settings["wallet_mode_of_payment"] = st["wallet_mode_of_payment"]
    elif st.get("wallet_mode_of_payment"):
        say(f"the payment method {st['wallet_mode_of_payment']} does not exist yet: run apply again after Member cash goes "
            "live, or a sale paid with Member cash still earns cash back")
    ensure("PP LYL Settings", "Default", settings, update=settings)
    # a tier is a customer group; its promotion EXCLUDES every other group, recomputed on every run (sample S5's rule)
    wh = [w["name"] for w in T.list("Warehouse", [["company", "=", CONF["company"]], ["is_group", "=", 0]], ["name"])]
    groups = [g["name"] for g in T.list("Customer Group", [["is_group", "=", 0]], ["name"])]
    seq = max((m.get("sequence_number") or 0 for m in T.list("Promotion Bonus Buys Master", [], ["sequence_number"])), default=0)
    for p in CONF["plans"]:
        if p["discount_percent"] <= 0:
            continue
        pid, seq = f"{p['customer_group']} {p['discount_percent']:g}%", seq + 1
        excl = {"table_promotion_exclusion_list": [{"source_type": "Customer Group", "source": g}
                                                   for g in sorted(groups) if g != p["customer_group"]]}
        ensure("Promotion Bonus Buys Master", pid, dict(excl, **{
            "id": pid, "description": f"{p['discount_percent']:g}% off the sale for {p['customer_group']}",
            "promotion_type": "Bonus Buys", "discount_type": "Percent", "discount_percent": p["discount_percent"],
            "minimum_bill_amount": 0, "minimum_quantity": 1, "active": 1, "sequence_number": seq,
            "table_applicability": [{"day": d, "enabled": 1, "start_time": "00:00:00", "end_time": "23:59:59"} for d in DAYS],
            "table_applicable_source": [{"source_type": "Warehouse", "source": w} for w in wh]}), update=excl)
    receipt_workflow()


def receipt_workflow():
    """⚠ ORDER MATTERS: a submit through the API that steps around the workflow lands in the FIRST submitted state, so
    *Overridden* is listed before *Verified* — a manager's direct submit is never recorded as verified."""
    mgr, svc, dt = "Stock Manager", CONF["integration_user"]["role"], "Purchase Receipt"
    states = [{"state": "PP LYL Draft", "doc_status": "0", "allow_edit": "Stock User"},
              {"state": "PP LYL Pending Verification", "doc_status": "0", "allow_edit": mgr},
              {"state": "PP LYL Overridden", "doc_status": "1", "allow_edit": mgr},
              {"state": "PP LYL Verified", "doc_status": "1", "allow_edit": mgr},
              {"state": "PP LYL Cancelled", "doc_status": "2", "allow_edit": mgr}]
    tr = [{"state": "PP LYL Draft", "action": "PP LYL Send for Verification", "next_state": "PP LYL Pending Verification", "allowed": "Stock User"},
          {"state": "PP LYL Draft", "action": "PP LYL Send for Verification", "next_state": "PP LYL Pending Verification", "allowed": mgr},
          {"state": "PP LYL Pending Verification", "action": "PP LYL Verify", "next_state": "PP LYL Verified", "allowed": svc},
          {"state": "PP LYL Pending Verification", "action": "PP LYL Override", "next_state": "PP LYL Overridden", "allowed": mgr},
          {"state": "PP LYL Verified", "action": "PP LYL Cancel", "next_state": "PP LYL Cancelled", "allowed": mgr},
          {"state": "PP LYL Overridden", "action": "PP LYL Cancel", "next_state": "PP LYL Cancelled", "allowed": mgr}]
    for s in states:
        ensure("Workflow State", s["state"], {"workflow_state_name": s["state"]})
    for a in sorted({t["action"] for t in tr}):
        ensure("Workflow Action Master", a, {"workflow_action_name": a})
    field = f"{dt}-workflow_state"
    if dt not in S.d["had_field"]:
        S.d["had_field"][dt] = T.get("Custom Field", field) is not None
        S.save()
    ensure("Workflow", WF, {"workflow_name": WF, "document_type": dt, "is_active": 1, "send_email_alert": 0,
                            "workflow_state_field": "workflow_state", "states": states,
                            # the maker may send their own receipt on; Verify, Override and Cancel refuse the person
                            # who made it (with no exception the maker could not even send it)
                            "transitions": [dict(t, allow_self_approval=int(t["action"] == "PP LYL Send for Verification"))
                                            for t in tr]})
    if not S.d["had_field"][dt] and T.get("Custom Field", field) is not None:
        S.made("Custom Field", field)
    take_submit(dt, CONF["receipt_workflow"]["keep_submit"])


def switches(on: int):
    with open(os.path.join(HERE, "manifest.json")) as fh:
        m = json.load(fh)
    todo = []
    for ra in m["registered_applications"]:
        # the user your service reads as, AND each followed record type ticked on: the shop writes a feed row only for a
        # ticked record type (recipes/event_feed.md), and the installer leaves every one unticked
        reg = T.get("Registered Application", ra["name"]) or {}
        ticked = [dict(r, enable=on) for r in reg.get("registered_application_events") or []]
        todo.append(("Registered Application", ra["name"], {
            "application_user": CONF["integration_user"]["email"] if on else None,
            "registered_application_events": ticked}))
    todo += [("Retail Remote App Key", f"{m['app']}:{k['key']}", {"consent_given": on, "enabled": on}) for k in m["remote_keys"]]
    for dt, name, fields in todo:
        try:
            T.update(dt, name, fields)
        except ShopError as e:
            say(f"not switched {dt}: {name} ({e.status})")
    say("switched", "on" if on else "off", "the feed registration and the member key")


def remove():
    switches(0)
    for dt, before in S.d["perms"].items():
        T.method(f"{PM}.reset_role_permissions", {"doctype": dt})
        for r in before:
            T.insert({"doctype": "Custom DocPerm", "parent": dt, "parenttype": "DocType", "parentfield": "permissions",
                      **{k: r[k] for k in ("role", "permlevel", "if_owner", *RIGHTS)}})
        say(f"restored permission rows of {dt}")
    for dt, name in reversed(S.d["made"]):
        if T.get(dt, name) is None:
            continue
        try:
            T.delete(dt, name)
            say(f"removed  {dt}: {name}")
        except ShopError as e:
            if dt == "User":      # a disabled user's key still signs in (recipes/integration_user.md): new keys, kept by no one
                T.method("ivendnext_mpos.api.v1.generate_keys", {"user": name})
                T.update(dt, name, {"enabled": 0})
            elif dt == "Role":    # a completed workflow step still names it, and only the site's Administrator sees those
                T.update(dt, name, {"disabled": 1})
            elif dt == "Promotion Bonus Buys Master":
                T.update(dt, name, {"active": 0})
            say(f"kept     {dt}: {name} ({e.message[:100]})")
    os.replace(BEFORE, BEFORE + ".removed")


def diff():
    def bare(rows):
        return [{k: v for k, v in r.items() if k != "name"} for r in rows]
    changed = sorted(dt for dt, before in S.d["perms"].items() if bare(before) != bare(custom_perms(dt)))
    print(json.dumps({"made_still_there": [[dt, n] for dt, n in S.d["made"] if T.get(dt, n) is not None],
                      "permission_tables_changed": changed}, indent=1))


def main(argv):
    global T, S
    T, S = Shop(os.environ["PP_BASE"], os.environ["PP_KEY"], os.environ["PP_SECRET"]), State()
    cmd = {"prepare": prepare, "apply": apply, "switch-on": lambda: switches(1), "switch-off": lambda: switches(0),
           "remove": remove, "diff": diff}
    if len(argv) < 2 or argv[1] not in cmd:
        sys.exit(__doc__)
    cmd[argv[1]]()


if __name__ == "__main__":
    main(sys.argv)
