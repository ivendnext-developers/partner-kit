"""The S1 till cases, shared by every binding (pure; no framework).

The same checks the core tests make (``test_core.py``: covered → success with months; not covered → info;
unknown item → warning; empty sale; sixty lines stay within the cap; an item's own term beats its group's;
duplicate lines named once), written once here so the hosted press and the remote wrapper are graded by the
SAME test (G4). ``contexts()`` gives the three contexts recorded from the bench's own ``build_context`` plus three
built from them."""

import copy
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent

# name -> (level, phrases that must appear in the body)
EXPECT = {
    "covered": ("success", ["PP-WRC-PHONE: 24 months", "AIRPODS-3: 12 months"]),   # own term 24 beats group 12
    "not_covered": ("info", ["CABLE-USBC-1M: not covered", "CASE-LEATHER: not covered"]),
    "unknown": ("warning", ["PP-NO-SUCH-ITEM: unknown item"]),
    "empty": ("info", ["There are no items on this sale yet."]),
    "sixty": ("warning", ["more"]),
    "duplicates": ("success", ["PP-WRC-PHONE: 24 months"]),
}


def contexts(dirpath=None) -> dict:
    d = pathlib.Path(dirpath) if dirpath else HERE / "contexts"
    out = {n: json.loads((d / f"{n}.json").read_text()) for n in ("covered", "not_covered", "unknown")}
    for c in out.values():
        c.pop("_recorded", None)
    out["empty"] = dict(copy.deepcopy(out["covered"]), sale_ref="pp-rec-empty", lines=[])
    out["sixty"] = dict(copy.deepcopy(out["covered"]), sale_ref="pp-rec-sixty",
                        lines=[{"item_code": f"ITEM-{i:03d}-WITH-A-LONG-CODE", "qty": 1.0, "uom": "Nos", "luid": f"l{i}"}
                               for i in range(60)])
    out["duplicates"] = dict(copy.deepcopy(out["covered"]), sale_ref="pp-rec-dupes",
                             lines=out["covered"]["lines"] * 3)
    return out


def failures(name: str, message: dict) -> list[str]:
    """[] when the message passes the case; else what is wrong."""
    level, phrases = EXPECT[name]
    bad = []
    if not isinstance(message, dict) or set(message) != {"title", "body", "level"}:
        return [f"not a message: {message!r}"[:200]]
    if message["level"] != level:
        bad.append(f"level {message['level']!r}, want {level!r}")
    bad += [f"body lacks {p!r}" for p in phrases if p not in message["body"]]
    if name == "duplicates" and message["body"].count("PP-WRC-PHONE") != 1:
        bad.append("a duplicated item is named more than once")
    if len(message["body"]) > 280 or len(message["title"]) > 60:
        bad.append("over the till's caps")
    return bad
