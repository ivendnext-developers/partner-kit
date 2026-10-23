"""What the shop's INSTALL refuses that its checker (``validate.py``, a byte-equal copy of the shop's own) passes.

The install screen runs ``validate.py`` first; then, inside the shop, the installer checks the manifest against the site
(``manifest_install._site_refusals_v2`` in the POS app) and installs in a fixed order. Three refusals come from that, and a
manifest that passes ``validate.py`` still fails at a shop on them (found on our test bench, 2026-10-18, sample S33, and
2026-10-23, sample S44):

1. **A field this manifest adds cannot be used by its own report, number card or chart.** The site check reads the shop's
   record type as it is BEFORE the install, so a field the same manifest adds there is not a field yet: *"not fields of
   <record type>: [...]"*. What it reads: a report's columns and filter fields, a number card's
   ``aggregate_function_based_on`` (not its filters), a chart's ``based_on``, ``value_based_on``, ``group_by_based_on``
   and ``aggregate_function_based_on``. On the manifest's own record types every field is there: never refused.
2. **A workspace cannot link the manifest's own report.** The installer makes workspaces before reports, so a shortcut
   to a report the same manifest makes cannot be saved: *"Could not find Row #n: Link To: <report>"*.
3. **A feed registration's description holds at most 140 characters.** The shop's Registered Application keeps its
   description in a field of 140 characters, and a longer one stops the install: *"CharacterLengthExceededError"*
   (found on our test bench, 2026-10-23, sample S44's first manifest).

    python3 tools/manifest/site_rules.py samples/s33_click_and_collect/manifest.json    # exit 0 = none; 1 = refused

Copied from no file: these mirror the POS installer's behaviour, read at ``ivendnext/iVendNext_PWA`` ``4c3f11b5`` (the
build our test bench and the beta shop run) and met there on the bench. A defect here is a defect there: report it with the Kit
defect form (feedback/README.md). ``tools/check/check.py``, ``tools/deploy/deploy.py`` and ``tools/selfcheck/selfcheck.py`` run it after
``validate.py``. Retire each rule when the shop's install no longer refuses it (asked of the POS board, 2026-10-18).
"""

from __future__ import annotations

import json
import sys

CHART_FIELDS = ("based_on", "value_based_on", "group_by_based_on", "aggregate_function_based_on")
DESCRIPTION_MAX = 140    # Registered Application's description field


def _rows(m, kind):
    rows = m.get(kind)
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def refusals(m: dict) -> list[dict]:
    """The install-time refusals ``validate.validate`` does not make: ``[{"where", "name", "reason"}]``."""
    if not isinstance(m, dict):
        return []
    own = {d.get("name") for d in _rows(m, "doctypes")}
    added = {(c.get("dt"), c.get("fieldname")) for c in _rows(m, "custom_fields")}
    out = []

    def not_added(where, name, dt, fields):
        if not isinstance(dt, str) or dt in own:
            return
        hit = sorted({f for f in fields if isinstance(f, str) and (dt, f) in added})
        if hit:
            out.append({"where": where, "name": name, "reason": f"not fields of {dt}: {hit} (the shop checks a report, "
                        "card or chart against the record type before the install, so a field this manifest adds is "
                        "not there yet)"})

    for i, r in enumerate(_rows(m, "reports")):
        cols = r.get("columns") if isinstance(r.get("columns"), list) else []
        flt = [f[0] for f in r.get("filters") or [] if isinstance(f, list) and f]
        not_added(f"reports[{i}]", r.get("name"), r.get("ref_doctype"), list(cols) + flt)
    for i, c in enumerate(_rows(m, "number_cards")):
        not_added(f"number_cards[{i}]", c.get("name"), c.get("document_type"), [c.get("aggregate_function_based_on")])
    for i, c in enumerate(_rows(m, "dashboard_charts")):
        not_added(f"dashboard_charts[{i}]", c.get("name"), c.get("document_type"), [c.get(k) for k in CHART_FIELDS])
    reports = {r.get("name") for r in _rows(m, "reports")}
    for i, w in enumerate(_rows(m, "workspaces")):
        for j, s in enumerate(w.get("shortcuts") or []):
            if isinstance(s, dict) and s.get("type") == "Report" and s.get("link_to") in reports:
                out.append({"where": f"workspaces[{i}].shortcuts[{j}]", "name": w.get("name"),
                            "reason": f"Could not find Row #{j + 1}: Link To: {s['link_to']} (the shop makes a workspace before the "
                                      "manifest's own reports: link a record type's list instead)"})
    for i, r in enumerate(_rows(m, "registered_applications")):
        d = r.get("description")
        if isinstance(d, str) and len(d) > DESCRIPTION_MAX:
            out.append({"where": f"registered_applications[{i}]", "name": r.get("name"),
                        "reason": f"the description is {len(d)} characters; the shop keeps at most {DESCRIPTION_MAX} "
                                  "(CharacterLengthExceededError at install)"})
    return out


if __name__ == "__main__":
    bad = refusals(json.load(open(sys.argv[1])))
    for r in bad:
        print(f"REFUSED {r['where']} ({r['name']}): {r['reason']}")
    sys.exit(1 if bad else 0)
