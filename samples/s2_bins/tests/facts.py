"""The facts a *Where is it?* answer must hold, never its sentence, so its words (``core.where_answer``) can be changed
with the tests green: each item named, in the sale's order, with the bin it sits in and the quantity there, or with no
bin when none holds it.

    lacks(body, [("Bananas", "AU-A1-01", 60), ("Paper towels", None, None)])   # -> [] when the answer holds them all

An item's part of the answer runs from its name (or code) to the next item's. Standard library only.
"""

from __future__ import annotations

import re


def _word(text: str) -> re.Pattern:
    return re.compile(rf"(?<![\w-]){re.escape(text)}(?![\w-])")


def _number(qty) -> re.Pattern:
    return re.compile(rf"(?<![\w.-]){re.escape(f'{float(qty):g}')}(?![\w]|\.\d)")


def lacks(body: str, expected) -> list[str]:
    """What ``body`` lacks of ``expected``, ``[(the item's name or code, its bin or None, its quantity or None)]``: [] when
    each item is named in that order with its bin and quantity in its own part, and an item of no bin names none."""
    bad, starts, pos = [], [], 0
    for item, *_ in expected:
        m = _word(item).search(body, pos)
        if not m:
            bad.append(f"{item!r} is not named after the item before it: {body!r}")
            starts.append(None)
            continue
        starts.append(m.start())
        pos = m.end()
    bins = [b for _, b, _ in expected if b]
    for n, (item, bin_, qty) in enumerate(expected):
        if starts[n] is None:
            continue
        end = next((s for s in starts[n + 1:] if s is not None), len(body))
        part = body[starts[n] + len(item):end]
        if bin_ is None:
            if any(_word(b).search(part) for b in bins):
                bad.append(f"{item!r} has no bin, yet its part names one: {part!r}")
            continue
        if not _word(bin_).search(part):
            bad.append(f"{item!r}'s part does not name its bin {bin_}: {part!r}")
        elif qty is not None and not _number(qty).search(part.replace(bin_, " ")):
            bad.append(f"{item!r}'s part does not give its quantity {qty:g}: {part!r}")
    return bad
