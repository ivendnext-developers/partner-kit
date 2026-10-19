"""S31's core: a parent item group in a coupon or a promotion, written out as its child groups. Pure: no shop, no network.

The till's coupon and promotion engines match an item's own item group exactly, so a row naming a parent group (say
*Supplements*) matches only items placed directly in that group, never those in *Supplements › Protein*. This works out
which child-group rows a record needs so that the parent covers its children.

Only two kinds of row are written out, because only there does a child row mean the same as the parent row:
  * a coupon's get rows (``Coupon`` → ``table_get_items``): the coupon applies when any row matches, and each child row
    copies the parent row's quantity, discount and flags;
  * a promotion's exclusion rows (``Promotion Bonus Buys Master`` → ``table_promotion_exclusion_list``): an excluded
    group is excluded wherever it sits.
A promotion's buy and get rows are each counted and filled on their own, so adding child rows there would change the
offer (more rows to meet, more lines to give). Those are never written out; a parent group there is FLAGGED.

Ownership. The rows have no marker field, so the service keeps its own list of the rows it added (``mine``). A row it did
not add is a person's and is never removed. A row it added that is gone was removed by a person: it is not added back.
"""

from __future__ import annotations

GROUP = "Item Group"
COUPON, PROMOTION = "Coupon", "Promotion Bonus Buys Master"

# record type -> {table: (the field naming the row's kind, the field naming the group, fields a child row copies)}
EXPAND = {
    COUPON: {"table_get_items": ("source_type", "source_key",
                                 ("quantity", "discount_type", "discount", "is_mandatory", "auto_add_in_transaction", "uom", "description"))},
    PROMOTION: {"table_promotion_exclusion_list": ("source_type", "source", ())},
}
FLAG = {PROMOTION: {"table_buy_items": ("source_type", "source_key"), "table_get_items": ("source_type_internal", "source_key")}}


def descendants(groups: dict, parent: str) -> list[str]:
    """Every group under ``parent`` (children, their children, …), in a stable order. ``groups`` = {name: parent name}."""
    kids: dict[str, list] = {}
    for g, p in groups.items():
        kids.setdefault(p, []).append(g)
    out, todo, seen = [], sorted(kids.get(parent, [])), {parent}
    while todo:
        g = todo.pop(0)
        if g in seen:          # a loop in the tree is not followed twice
            continue
        seen.add(g)
        out.append(g)
        todo += sorted(kids.get(g, []))
    return out


def plan(doctype: str, doc: dict, groups: dict, mine: dict, removed: set) -> dict:
    """What one record needs.

    ``groups``: {group: its parent}. ``mine``: {(table, child group): the parent group it was added for}, the rows this
    service added to THIS record. ``removed``: {(table, child group)} rows it added that a person removed.

    Returns {"add": {table: [new row, …]}, "drop": {table: [child group, …]}, "mine": the new ``mine``,
    "removed": the new ``removed``, "flags": [why, …]}. ``drop`` lists only rows this service added whose parent row is
    gone; a person's row is never in it."""
    is_parent = {p for p in groups.values() if p}
    out = {"add": {}, "drop": {}, "mine": dict(mine), "removed": set(removed), "flags": []}

    for table, (kind, key, copy) in EXPAND.get(doctype, {}).items():
        rows = [r for r in doc.get(table) or [] if r.get(kind) == GROUP and r.get(key)]
        present = {r[key] for r in rows}
        # a row this service added that is gone: a person removed it, so it is not added back
        for (t, child) in list(out["mine"]):
            if t == table and child not in present:
                del out["mine"][(t, child)]
                out["removed"].add((t, child))
        parents = [r for r in rows if r[key] in is_parent and (table, r[key]) not in out["mine"]]
        # every child the listed parents cover, and the first parent row that covers it
        wanted: dict = {}
        for p in parents:
            for child in descendants(groups, p[key]):
                wanted.setdefault(child, p)
        # a child no listed parent covers any more is free to come back if a parent lists it again
        out["removed"] = {(t, c) for (t, c) in out["removed"] if t != table or c in wanted}
        for child, p in wanted.items():
            if (table, child) not in out["mine"] and child not in present and (table, child) not in out["removed"]:
                row = {kind: GROUP, key: child, **{f: p.get(f) for f in copy if p.get(f) is not None}}
                out["add"].setdefault(table, []).append(row)
                out["mine"][(table, child)] = p[key]
                present.add(child)
        # only the service's own rows that no listed parent covers any more are dropped; a person's row never is
        for (t, child) in sorted(out["mine"]):
            if t == table and child not in wanted and child in present:
                out["drop"].setdefault(table, []).append(child)
                del out["mine"][(t, child)]

    for table, (kind, key) in FLAG.get(doctype, {}).items():
        for r in doc.get(table) or []:
            if r.get(kind) == GROUP and r.get(key) in is_parent:
                out["flags"].append(f"{doc.get('name')}: {table} names the parent group {r[key]!r}; it matches only items "
                                    "placed directly in it. A child row here would change the offer, so it is not written: "
                                    "list the child groups yourself, or set the offer on the items")
    return out


def table_after(doc: dict, table: str, kind: str, key: str, add: list, drop: list) -> list:
    """The whole table to write back: every row as it is (by its name), less the dropped rows of ours, plus the new rows."""
    keep = [r for r in doc.get(table) or [] if not (r.get(kind) == GROUP and r.get(key) in drop)]
    return keep + add
