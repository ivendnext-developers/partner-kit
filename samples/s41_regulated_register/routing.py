"""Which books a line enters: a model of the register door's own rule (the register books page, §2, §5), so a partner can test a
data set's routing before the door is installed. The door evaluates conditions with the POS app's save-rule code; this
model follows that code: a number or tick-box column compares as a number, any other column as trimmed text (= and !=),
and is set / is not set test for a value.

    from routing import books_for
    books_for(data_set, line)   # -> the ids of the books the line enters

A book takes a line when the line's item is in the book's items (its class on the book's own axis is one of the book's
classes, or its item group one of the book's groups) and every one of the book's conditions holds on the line. One line
may enter several books. A correction, a count and an opening balance go to the book of the line they concern, and a
return follows the books its original sale entered, whatever those books' conditions say."""

from build import NUMERIC_COLUMNS, slots


def _empty(v):
    return v is None or v == [] or (isinstance(v, str) and not v.strip())


def _num(v):
    try:
        return float(str(v).replace(",", "")) if v not in (None, "") else 0.0
    except ValueError:
        return 0.0


def holds(line, cond, slot_of=None):
    field = cond["field"]
    if field.startswith("detail:"):
        field = (slot_of or {})[field[7:]]
    value, op, wanted = line.get(field), cond["operator"], cond.get("value")
    if op == "is set":
        return not _empty(value)
    if op == "is not set":
        return _empty(value)
    if op in ("=", "!=") and field not in NUMERIC_COLUMNS:
        same = str(value if value is not None else "").strip() == str(wanted).strip()
        return same if op == "=" else not same
    a, b = _num(value), _num(wanted)
    return {"=": a == b, "!=": a != b, ">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b}[op]


def class_of(book, line):
    """The line's class on the book's axis: the door copies it from the item when it writes the line. A fixture line
    gives ``item_classes`` ({axis: class}) for an item on several axes, or ``item_class`` for one."""
    axis = (book.get("class_source") or {}).get("axis")
    return (line.get("item_classes") or {}).get(axis, line.get("item_class"))


def in_items(book, line):
    if book.get("classes"):
        return class_of(book, line) in book["classes"]
    return line.get("item_group") in (book.get("item_groups") or [])


def books_for(ds, line):
    """The books a NEW movement's line enters. A correction, count or opening is booked into the book of the line it
    concerns (``line["book"]``); a return into the books its original entered (``line["original_books"]``)."""
    if line.get("kind") in ("Correction", "Count", "Opening"):
        return [line["book"]]
    if line.get("kind") == "Return" and "original_books" in line:
        return list(line["original_books"])
    slot_of = slots(ds)
    return [b["id"] for b in ds["books"]
            if in_items(b, line) and all(holds(line, c, slot_of) for c in b.get("conditions", []))]
