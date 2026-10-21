#!/usr/bin/env python3
"""Every extension point has at least one card in the needs catalogue, and so a row in chapter 16's "Possible today".

    python3 .github/scripts/chapter16_rows.py [<kit root>]       # exit 0 = every contract page has a card on its door

Chapter 16's "Possible today" list is built by the site from the cards in needs/ (tools/needs/needs.py), so this check reads
the cards' `door`, not the chapter. A page in `contracts/pages/` is an extension point; its title (the first heading) is
mapped to a door in TITLE_DOOR below, held as data so that no card can satisfy it by accident (a page whose door is `manifest`, a
manifest kind, is satisfied by any ready manifest card). Each mapped door must be the
door of at least one card whose verdict is Ready or Ready, with limits. A contract page whose title is not in the map fails
too: adding a contract, its door and its first card is one change (for a `manifest` page, any ready manifest card is enough). Reads local files only; no network, no secret.
"""
from __future__ import annotations

import pathlib
import sys

TITLE_DOOR = {
    "Partner check": "check-before-payment",
    "Partner capture": "capture-on-event",
    "Desk action": "desk-action",
    "Document check": "document-check",
    "Event feed": "event-feed",
    "Field rules": "field-rules",
    "Fiscal reader": "fiscal-reader",
    "Label layout": "label-layout",
    "List mark": "manifest",           # a manifest kind (list_marks): any ready manifest card satisfies this door
    "Partner fulfil — a code your service makes for a paid sale line": "fulfil-at-sale",
    "Partner page": "partner-page",
    "The iVendNext Remote Gateway Contract — `paygw/1` (Payment Gateway Interface 1)": "payment-connector",
    "Pricing extension point": "sandboxed-function",
    "Print template readers — `ivn_rows` and `ivn_value`": "manifest",   # read by a manifest's print format: as above
    "Receipt: the shop's own lines, WhatsApp, a checked layout": "receipt",
    "Remote till key": "till-key",
    "Save rules": "save-rules",
    "Scan source": "scan-source",
    "Wallet extension point": "wallet",
}


def main() -> int:
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    sys.path.insert(0, str(root / "tools" / "needs"))
    import needs
    open_doors = {c.door for c in needs.load(root) if c.status in ("ready", "ready-with-limits")}
    pages = sorted((root / "contracts" / "pages").glob("*.md"))
    missing = []
    for page in pages:
        title = next((l[2:].strip() for l in page.read_text("utf-8").splitlines() if l.startswith("# ")), page.stem)
        door = TITLE_DOOR.get(title)
        if door is None:
            missing.append(f"{page.name} ({title}): no door mapped in TITLE_DOOR")
        elif door not in open_doors:
            missing.append(f"{page.name} ({title}): no Ready card has door {door}")
    for x in missing:
        print("NO CARD for an extension point: " + x)
    print(f"chapter 16: {len(pages)} extension point(s) checked, " + ("each has a card" if not missing else f"{len(missing)} without one"))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
