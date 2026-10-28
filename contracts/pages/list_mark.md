<!-- Source: ivendnext/iVendNext_PWA docs/extending/list_mark.md @ 60147699cce4, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# List mark

**Contract:** [`list_mark.v1.schema.json`](../extension_contracts/list_mark.v1.schema.json)
· samples: [`samples/list_mark/`](../extension_contracts/samples/list_mark/)
· code: `business_logic/list_mark.py` (`validate_mark`, `extend_bootinfo`), `public/js/list_mark.js`.

## 1. What it is

A coloured label on a row of a shop's Desk list, shown when the row's values say so: products on
promotion marked green *On promotion*, customers on credit hold red *Credit hold*, suppliers awaiting
documents gray *Docs due*. A System Manager declares it as a **Retail List Mark**; one small Desk script
of ours draws it. No partner JavaScript runs in Desk, and nothing is saved or refused by a mark: it is
display only.

Desk already colours a row's label from a workflow, a status field or the record type's own list
script. A partner can add none of those to a shop's records (a prefixed field is never `status`; a
workflow or a list script on a shop's record type is refused), which is the gap a mark fills.

## 2. What is declared

| Setting | Value |
|---|---|
| Record type | a record type that is **not submitted and has no active workflow** (Item, Customer, Supplier, Batch, Item Price, your own record types) |
| Only when | 1 to 3 conditions `field operator value`, all of which must hold: `=`, `!=`, `>`, `>=`, `<`, `<=`, `is set`, `is not set`; any field of the record type, standard or prefixed, except a password or a long text |
| Label | at most 24 characters, plain text, translated when drawn |
| Colour | `green`, `blue`, `orange`, `red`, `gray` or `purple` |
| Sequence, Enabled | when two marks match a row, the lower sequence shows; a mark that is off shows nowhere |

At most **5 marks** per record type. With nothing declared, the Desk script wraps nothing and makes no call.

**Refused when the mark is saved**, each in its own words:
- a submitted record type, or one with an active workflow — *a submitted record's label says what can be
  done with it; a mark goes on a record type without one*;
- a table or a single record type;
- a field the record type does not have, or a virtual one;
- a password or long text field;
- a label over 24 characters, or holding any of `< > & " ' ` ` (Desk writes the label into the form's
  header and a list dot's title as HTML);
- a colour not in the list;
- a sixth mark on one record type.

## 3. Where the mark sits in Desk's order

Desk picks a row's label in this order: an unsaved record · a workflow state · a **document state** of
the record type matched to its `status` · **the first matching mark** · the record type's own list
script · the framework's defaults (*Enabled* / *Disabled*, any `status`).

The mark comes **before** the record type's own list script because some lists always answer: Supplier's
answers *On Hold*, Batch's always shows its expiry. A mark that should yield to the shop's own labels says
so in its conditions: `disabled = 0` keeps *Disabled* on a disabled item.

Clicking the label filters the list on the mark's conditions (a condition whose value holds `|` is left
out of the filter, which Desk splits on that character).

## 4. Who sees it

The marks travel with the user's boot info (read at each Desk page load; the declarations themselves are one cached read) to every Desk user who may read
the record type — **and only the marks whose every condition field the user may read**. A condition may
read a field above permission level 0; a user below that level never receives the mark, its field or its
value, so it can never mark a row for them. (Leaving it to the row is not enough: a list's query drops
such a field, but the framework's answer to a Save sends the whole record back to the form.) The script
also draws no mark when a condition's field is absent from the row, so an `!=` or *is not set* never
marks a row that does not carry the field. (A Desk action's conditions are held to level 0, because a
press reveals a bit of the field; a mark is simply not sent to such a user.)

## 5. Bounds, stated

- **Desk colours a label, not a row.** A coloured row background is not offered: a tinted row reads as a
  selected one.
- **The label function is the framework's, for every place Desk shows a record's label**, so a mark also
  shows in the form's header and the sidebar, not only the list.
- **The fields a mark reads are added to the list view's own request** (no second request). The report
  view shows no label column at all, so no mark (walked on `:8095`); the image view builds its own field
  list, so there a mark shows only when its fields are already among them. Answering *yes* to "does this record type have a label?" also moves a plain `status` column
  into the label column on a list that had none.
- A mark is checked on each row as Desk draws it: at most 5 marks × 3 comparisons in the browser.
- A comparison (`>`, `<`, …) reads numbers only: a date field can be matched with `=` or *is set*, not
  "this month" (an *expiring* mark needs a check field the partner keeps current).
- A record type renamed after its mark was saved: the mark is skipped (never an error) and returns
  under the new name when any mark is next saved.
- A virtual field is refused (a list row never carries one). A record type made submittable after its
  mark was saved shows Desk's own *Draft* / *Submitted* again at once; the mark leaves the boot info when any mark is
  next saved.
- In a manifest, two marks on one record type need two labels (an update matches a mark by its record
  type and label); to mark on *A or B*, write two marks with two labels.
- **Desk only.** The till never draws a Desk list; a product on promotion at the till is a field rule
  ([fields.md](fields.md)).

## 6. In a manifest

`list_marks` (manifest version 2), one object per mark:

```json
"list_marks": [
  {"record_type": "Item", "label": "On promotion", "colour": "green", "sequence": 10,
   "conditions": [{"field": "pp_on_promotion", "operator": "=", "value": "1"},
                  {"field": "disabled", "operator": "=", "value": "0"}]}
]
```

The manifest checker refuses what needs no site (the colours, the label, the conditions' shape, a sixth
mark on one record type); the record's own checks run again at install and refuse the rest word for word.
Each mark arrives **switched off**; the shop switches it on in **Retail List Mark**. An uninstall removes
it with nothing left behind (package_install.md).
