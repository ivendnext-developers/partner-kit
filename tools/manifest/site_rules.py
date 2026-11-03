"""What the shop's INSTALL stops on that its checker (``validate.py``, a byte-equal copy of the shop's own) passes.

The install screen runs ``validate.py`` first; then the installer saves each record, and iVendNext's own save rules stop the
install, which takes back what it had made. Two of those stops are worth knowing before you send the app, so ``ivn check`` says
them first, in the words the install would use:

1. **A feed registration's description holds at most 140 characters.** The shop's Registered Application keeps its description
   in a field of 140 characters: *"'Application Description' ... will get truncated, as max characters allowed is 140"*.
2. **A record type's name holds at most 61 characters.** iVendNext keeps a table for each: *"Doctype name is limited to 61
   characters"*. A long app name with a sample's long names can reach it.

    python3 tools/manifest/site_rules.py samples/s33_click_and_collect/manifest.json    # exit 0 = none; 1 = refused

Copied from no file: each was run against the installer on our test bench at POS build 2.1.0.679, and each stopped the install in
those words. A defect here is a defect there: report it with the Kit defect form (feedback/README.md). ``tools/check/check.py`` and
``tools/selfcheck/selfcheck.py`` run it after ``validate.py``. Retire a rule when the shop's install no longer stops on it.
"""

from __future__ import annotations

import json
import sys

DESCRIPTION_MAX = 140    # Registered Application's description field
NAME_MAX = 61            # a record type's name


def _rows(m, kind):
    rows = m.get(kind)
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def refusals(m: dict) -> list[dict]:
    """The install's stops ``validate.validate`` does not make: ``[{"where", "name", "reason"}]``."""
    if not isinstance(m, dict):
        return []
    out = []
    for i, d in enumerate(_rows(m, "doctypes")):
        name = d.get("name")
        if isinstance(name, str) and len(name) > NAME_MAX:
            out.append({"where": f"doctypes[{i}]", "name": name,
                        "reason": f"Doctype name is limited to {NAME_MAX} characters ({len(name)}): use a shorter app name"})
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
