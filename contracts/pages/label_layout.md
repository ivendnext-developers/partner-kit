<!-- Source: ivendnext/iVendNext_PWA docs/extending/label_layout.md @ 60147699cce4, copied unchanged except the links, one bug id and one row id on the product's board: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Label layout

**Contract:** [`label_layout.v1.schema.json`](../extension_contracts/label_layout.v1.schema.json)
· samples: [`samples/label_layout/`](../extension_contracts/samples/label_layout/)
· code: `business_logic/label_print.py` (`validate_layout`, `label_context`, `till_price`, `scale_context`, `render_sheet`),
`api/mpos_label.py`, the till's `public/js/mpos_label.js` (+ `counter_hardware.js` `printLabel` for a `zpl` layout),
`business_logic/label_network.py` (a network label printer, §5c).

## 1. What it is and when it fires

A shelf or item label printed from the till: the item, its barcode, its price, and for a batch item its batch
and expiry. A **Retail Label Layout** is data: HTML with placeholders from a closed list. The till fills it on
the server and opens it in the device's own print dialog, so it prints on any printer the phone, tablet or
counter can already reach. A `zpl` layout is Zebra printer commands instead: a counter till sends them, through
its print agent, to the label printer its POS Terminal names. Either kind can instead go from the server to a
**network label printer** the till's POS Terminal names, from any frame (§5c). A weighed pre-pack can also get a
**scale label**, its own weight and price in the barcode (§5d). No code is installed.

It fires when the cashier presses **Print label** on an item's card or on a basket line (phone, counter and
tablet alike), picks the layout (when the store keeps several), the batch (a batch item) and how many, and
presses **Print**. From a basket line the sheet offers that line's own lots, the first chosen (a line with no
lot: the store's lots on hand, as the item card), and the label is in **that line's unit** (a strip sold from a
box: one strip, §3), with the details typed on the line for a layout that prints one.

## 2. Version

Version 1. Kinds `html` and `zpl` (added with the basket-line entry, the lot label and the manifest kind,
lane `plabel2`: a layout written for version 1 is unchanged). Lane `plabelscale` adds two placeholders to the
closed list, `{weight}` and `{unit_price}`: a layout that holds neither is unchanged, and a checker copy older than
this one refuses a layout that holds them. Lane `pb10label` adds two **named** placeholders beside the list,
`{item.<fieldname>}` and `{detail.<attribute>}`, and prints a basket line's label in that line's unit: a layout that
holds neither is unchanged, the item card's label is unchanged, and a checker copy older than this one refuses a
layout that holds them.

## 3. What you declare

A System Manager adds one **Retail Label Layout** per label stock, in iVendNext Desk, and grants **Print** on
Retail Label Layout to the roles that may print labels (Role Permission Manager). Without it, the till's
Print label row is dimmed with its reason.

| Field | What it holds |
|---|---|
| Layout name | the name the till shows |
| Kind | `html` (the device's print dialog) or `zpl` (a counter till's label printer) |
| Enabled | switched on |
| Width (mm) · Height (mm) | one label, 10 to 150 mm each |
| Labels per row | 1 for a roll; up to 10 side by side on a sheet |
| Template | HTML with the placeholders below, and no others |

**Placeholders:** `{item_code}` · `{item_name}` · `{barcode}` · `{barcode_svg}` (a Code-128 drawn inline, on
the server) · `{price}` · `{currency}` · `{uom}` · `{batch_no}` · `{expiry_date}` · `{manufacturing_date}` ·
`{weight}` · `{unit_price}` · `{store}`, and two named ones:

- **`{item.<fieldname>}`** — one of the item's own fields, by its field name (`{item.custom_strength}`,
  `{item.custom_route}`, an allergen list): **at most three** per template, each a **Data, Select, Int or Check**
  field open to every role (permission level 0) — the same types and the same three the till's field rules show
  on screen and on the receipt ([`fields.md`](fields.md)). A money field (Currency, Float) is never one: the
  label's price is `{price}`, the till's own.
- **`{detail.<attribute>}`** — **one** detail typed on the basket line (a dispensing label's dose): the name of an
  active **Transaction Item Attribute**, as the till records it per line (*Item details*). From the item card,
  where there is no line, it prints nothing.

Every value is escaped; none is code. Any `{…}` in the template is read as a placeholder, so a
`<style>` block with braces is refused: style with `style="…"` attributes.

**Where each value comes from:**

- **`{price}`** is the till's own price for one of the unit the till sells the item in (a Pack-sold article:
  one Pack), at the cashier's store, to its cash customer: the price the till charges a walk-in today,
  promotions included. `{currency}` is that price's currency; `{uom}` is that unit. ⭐ **From a basket line it is
  that line's unit** (a box-sold medicine sold by the strip: one strip, at the till's price for a strip), checked
  as the till checks a unit change: a weighed, serial or bundle article keeps its unit, and a unit not on the
  item's list is refused (§4). A scale label is always in the weighed article's stock unit. A line ordered from
  another store is labelled at THIS store's price for that unit: a label is this shelf's.
- **`{barcode}`** is the item's own barcode for that unit (or its barcode with no unit). ⭐ In a line's unit that
  is not the one the till rings a new line in, only **that unit's own barcode** is printed: the item's barcode
  with no unit rings the default unit when scanned (a box), so beside a strip's price it would ring another price.
  A layout that prints a barcode, for a unit with no barcode of its own, is refused, naming the fix (§4); such a
  label prints no lot code either (the till asks for the lot at the scan). It carries no price:
  scanned, the till prices it exactly as it prices the item, so it rings the printed price today and the
  current price after a change. ⚠ An item with a barcode mask gets its own barcode too, never one built by the
  mask: a mask's Price segment would set the price at the till for as long as the label hangs on the shelf, and
  its weight would skip the scale. A weighed item's label scans to the scale, as the item does.
  ⭐ **The one exception — a lot label.** When a batch is chosen and the item's own barcode mask has **no Price
  and no Quantity segment** (only Item Barcode or Item Code, Serial or Batch, Skip), `{barcode}` is that mask,
  filled by the engine with the lot: scanned, the till rings this item, this lot, one unit, at the printed
  price. It is printed only after the till's own scan step reads it back as this item and this lot; otherwise
  (a lot longer or shorter than the mask's segment, a weighed article, a mask carrying a price or a quantity)
  the label keeps the item's own barcode. An item with no barcode of its own may carry a mask that holds only
  its code. ⚠ The read-back is true the day the label prints: a mask edited later (a Price segment added) re-reads
  every lot label on the shelf, as it re-reads every scale label — keep a lot mask price-free.
- ⭐ **The one label that carries money — a scale label (§5d).** For a weighed item whose barcode mask has a
  Quantity segment, Print label also offers a **Scale label**: the weight is typed, and `{barcode}` is the item's
  own mask filled by the engine with that weight and the pack's price. On it `{price}` is the pack's total (the
  till's own one-unit price × the weight, at the currency's minor unit), `{unit_price}` is the till's price for one
  unit, and `{weight}` is the weight at the mask's own decimals, in the site's number format (a gram mask: `0.750`).
  On a shelf label `{unit_price}` is the same as `{price}` and `{weight}` is empty. A scale label is printed only
  on a layout that holds `{weight}`: a layout written for shelf labels would otherwise show the pack's total where
  it shows a price per unit.
- **`{expiry_date}` · `{manufacturing_date}`** are the batch's own dates, in the site's date format.
- **`{store}`** is the cashier's store.
- **`{item.<fieldname>}`** is the item's field as it reads when the label prints (an Int 0 prints `0`, a Check
  `1` or `0`). Checked when the layout is saved and read again when it prints: a field the shop deleted, retyped,
  made virtual or limited to some roles since prints nothing in its place, with no refusal.
- **`{detail.<attribute>}`** is the value typed on the basket line, cut at 140 characters. It prints nothing when
  the line has none typed, when the label comes from the item card (there is no line), or when the attribute was
  made inactive since the layout was saved: a line detail is never required. A layout that must not print without
  one is the shop's to check before printing. ⛔ It rides only the
  till's print request, never an address: the page the device's dialog prints comes back in that answer (an
  address sits in server logs and the browser's history, and a dose is a patient's).

## 4. Every refusal, in the product's words

**When the layout is saved:** *"⟨placeholder⟩ is not a label placeholder. Use: ⟨the list⟩."* · *"A label
template takes placeholders like {item_name}, not code."* · *"A label template cannot hold scripts, frames,
forms or event handlers."* · *"Width must be between 10 and 150 mm."* (Height the same) · *"Labels per row
must be between 1 and 10."* · *"A label layout needs a template."* · *"A label template holds at most 20000 characters."*
· for `zpl`: *"A zpl label template starts with ^XA and ends with ^XZ."* · *"A zpl label template draws its barcode
with the printer's own barcode command over {barcode}, not {barcode_svg}."* · named placeholders: *"A label prints at
most 3 of the item's fields, not ⟨fields⟩."* · *"⟨field⟩ is a ⟨type⟩ field. Only Data, Select, Int and Check fields
can be shown."* · *"Item has no field ⟨field⟩."* · *"⟨field⟩ is a field only some roles can see, so a label can't
print it."* · *"⟨field⟩ is not stored on the item, so a label can't print it."* (a virtual field) · *"A label prints one line detail, not ⟨details⟩."* · *"⟨attribute⟩ is not a line detail the till
records. Use the name of an active Transaction Item Attribute."*

**At the till:**

| What happened | The cashier reads |
|---|---|
| No Print right on Retail Label Layout | *"You don't have permission to print a label. Ask a manager."* |
| Offline | *"Labels need a connection."* |
| No enabled layout (the row is dimmed with it, whatever the cashier's rights) | *"No label layout is set up. Ask an admin."* |
| Only `zpl` layouts, and this device cannot reach a label printer (none named on its till, the print agent not answering, or the name not listed exactly) | *"The store's label layouts print on a label printer, and this ⟨device⟩ can't reach one."* |
| A value a `zpl` layout prints holds `^` or `~` (a command to a Zebra printer) | *"⟨value⟩ holds ^ or ~, which a Zebra label printer reads as a command. Change it in iVendNext Desk, or print a sheet label."* |
| The label printer did not take the job | *"The label printer didn't take the labels. Check it is on and connected, then try again."* |
| The layout prints a barcode the item does not have | *"⟨item⟩ has no barcode to print. Add one to the item in iVendNext Desk."* |
| From a basket line in a unit with no barcode of its own (not the unit the till rings a new line in), on a layout that prints a barcode | *"⟨item⟩ has no barcode for ⟨unit⟩. Add one for that unit to the item in iVendNext Desk, or print a layout without a barcode."* |
| From a basket line in a unit the article does not sell in (weighed, serial, a set, a unit off its list) | the till's own unit refusal, e.g. *"⟨item⟩ can't be sold in "⟨unit⟩": Sold by weight. The unit comes from the scale."* · *"⟨item⟩ isn't sold in "⟨unit⟩". Pick one of its listed units."* |
| The item's barcode starts like a scale label, so the till would read it through a barcode mask (another item, or a price in the code) | *"The till reads ⟨item⟩'s barcode as a scale label, so it can't go on a shelf label."* |
| A scale label (§5d) that the till would read as another weight or price than the one printed | *"⟨item⟩'s scale label would scan as ⟨weight⟩ for ⟨currency price⟩, not what was weighed. Weigh the pack again, or print a shelf label."* |
| A scale label whose code does not read back as this item (no barcode, another item) | *"The scale label for ⟨item⟩ can't be made. Check the item's barcode and barcode mask in iVendNext Desk."* |
| A scale label for an item with no barcode mask that carries a weight (the choice is dimmed with it) | *"⟨item⟩ has no barcode mask that carries a weight. Ask an admin to add one in iVendNext Desk."* |
| A scale label asked for by someone without the permission to type a sale's weight (dimmed with it) | *"Manual weight entry needs the manual-weight permission. Ask a manager."* |
| A scale label with no weight typed | *"Type the weight of the pack."* |
| A scale label with a weight finer than the mask holds (0.7504 on a gram mask) | *"This label holds a weight to ⟨n⟩ decimal places. Type the weight again."* |
| A scale label on a layout with no `{weight}` | *"The layout ⟨layout⟩ doesn't print the weight, so it can't be used for a scale label. Pick a layout that does."* |
| A scale label for an item that is not sold by weight | *"⟨item⟩ is not sold by weight, so it has no scale label."* |
| A count outside 1 to 100 | *"Print between 1 and 100 labels at a time."* |
| The article is disabled | *"Item ⟨item⟩ is not on sale."* |
| A template article (its variants are labelled) | *"Pick a size or colour first. A label is printed for one variant."* |
| A batch that is not the article's | *"Batch ⟨batch⟩ is not a batch of ⟨item⟩."* |
| The layout picked was disabled since | *"Label layout ⟨layout⟩ is not available."* |
| The till returned no price for the article | *"The till could not price ⟨item⟩."* |
| The print window was closed before the label reached it | *"The print window was closed. Nothing was printed."* |
| The browser blocked the print window | *"This ⟨device⟩ blocked the print window. Allow pop-ups for this site, then try again."* |
| Network label printer (§5c): none named on this device's till | *"No network label printer is named for this till. Ask an admin."* |
| Network label printer: its record was deleted, or holds no address | *"The label printer ⟨printer⟩ is no longer set up. Ask an admin."* |
| Network label printer: no answer within 5 seconds (one attempt) | *"The label printer ⟨printer⟩ didn't answer. Check it is on and connected, then try again."* The sheet stays open with the labels. |
| Network label printer: the print server refused the job | *"The label printer ⟨printer⟩ didn't take the labels. Check it is on and connected, then try again."* |
| Network label printer on its raw port (9100), asked for a sheet layout (the sheet does not offer it there) | *"The label printer ⟨printer⟩ takes zpl layouts only. Print this layout on this device."* |
| Network label printer: the server could not render the sheet label as a PDF | *"The labels couldn't be made ready for the label printer ⟨printer⟩. Try again, or print them on this device."* |

## 5. Consent, and when it is down

No outside service is called, so there is no consent to record. The one connection the server opens is to the
network label printer the till's POS Terminal names (§5c); when it is down, the cashier reads the sentence in §4.

## 5b. A Zebra (`zpl`) layout at the counter

1. On the till's **POS Terminal**, set **Label Printer** to the printer's name exactly as the till's computer
   lists it. The till must be wired (a Hardware Profile, and the print agent with the site's certificate),
   as for its receipt printer; the receipt printer is never used for labels.
2. Add a Retail Label Layout of kind `zpl`: the template is ZPL, `^XA` to `^XZ`, with the placeholders filled as
   plain text. Draw the barcode with the printer's own command over `{barcode}` (for example `^BCN,60^FD{barcode}^FS`).
   For text beyond Latin letters, start with `^CI28`.
3. At that till, Print label offers the `zpl` layout beside the sheet layouts; a device that cannot reach the label
   printer (a phone, a tablet, a till with no label printer named or its agent not answering) never sees it. The till says *Handed to the label printer* — never *Printed*.

⚠ The `^`/`~` refusal holds for ZPL's default prefixes: a layout that moves them (`^CC`, `~CC`, `~CT`) or decodes hex in
its fields (`^FH`) is the author's to keep safe. The print agent sends one print at a time: a label asked for while a
receipt is printing is refused (*"The label printer didn't take the labels…"*) — press Print again.

⚠ No Zebra printer and no print agent were on any bench when this was built: what is proven is the commands the
server writes and the job the till hands its agent, never the paper.

## 5c. A network label printer, in every frame

1. In iVendNext Desk, add a **Network Printer Settings** record for the printer. Its **Port** says what the
   printer is:
   - **9100** — a label printer on its own address taking raw commands (a network Zebra): **Server IP** = the
     printer's address. It takes `zpl` layouts only.
   - **any other port** (631 for a print server) — a print server's queue: **Server IP** and **Port** = the print
     server's, **Printer Name** = its queue. It takes both kinds: a `zpl` layout as a raw document, a sheet layout as
     a PDF at the label stock's size (a Zebra queue with the Zebra driver prints both).
2. On the till's **POS Terminal**, set **Network Label Printer** to that record. Only a System Manager sets the
   address: the till sends the route and its own device, never an address.
3. At that till, on the phone, the tablet or the counter, Print label offers it. A `zpl` layout goes to it; at a
   counter whose own label printer is ready (§5b), a `zpl` layout still goes there first. Where the printer takes
   sheet layouts too, a sheet layout offers a **Printer** choice: the network label printer (first) or this
   device's print dialog. The till says *Handed to the label printer ⟨printer⟩* — never *Printed*: a print server
   that queued the job says nothing about the paper. Every layout reaches it: a `zpl` layout as raw commands, a sheet
layout as a PDF (on a print-server record), and a scale label (§5d) the same way, filled the same.

⚠ **Setting the record up.** The Desk's Network Printer Settings form lists a print server's queues, and saves,
only where the site's bench has the `pycups` library installed (the same as for server-printed receipts); the
label route itself does not need it. **Printer Name** is required and the form fills its list from a print
server, so a port-9100 record (a printer, no print server) is created with Data Import, any name in Printer Name.

⚠ **Reach.** The SERVER opens the connection, exactly as the server receipt route does, so a label reaches only a
printer the server can reach: an on-site server, a VPN to the store, or a printer exposed over IPP. A site hosted on
Press cannot reach a printer on the store's own network; there, use the device's print dialog or the counter's label
printer. One attempt, a 5-second deadline, no retry.

⚠ Proven on a print server and a raw listener in containers beside the walk bench (the bytes each received), never on
paper from a real Zebra.

## 5d. A scale label (a weighed pre-pack), in every frame

A deli or fruit counter weighs a pack and prints a label with the pack's weight and price inside the barcode; the
till then charges exactly that when the label is scanned.

1. The item is a **weighed** item, and its **Barcode Mask** (iVendNext Desk) has a **Quantity** segment (an Item
   Barcode or Item Code segment, a Price segment if the price is to ride the code, and the Quantity). A price-only
   mask is no scale label: its scan rings one unit, so stock would fall by one and not by the pack.
2. In Print label, a weighed item's sheet has a **Label** choice, *Shelf label* or *Scale label*. *Scale label* shows
   a **Weight** field, typed in every frame; it is dimmed, with its reason, for an item whose mask carries no
   weight or for someone without the permission to type a sale's weight (*manual-weight*).
3. The server writes the label with the engine's own barcode encoder, then **reads it back the way the till will**:
   the till's mask decode, its barcode lookup, and finally the line the till would book from a scan of that code.
   The label prints only if that line is the printed weight at the printed total; otherwise nothing prints and the
   sentence in §4 says what the till would have charged.
4. The weight must be exact at the mask's own unit: 0.7504 kg on a gram mask is refused (never rounded), so the
   weight printed and the weight encoded are the one typed. A lot-tracked item's lot rides the code only where the
   mask has a Serial or Batch segment. Where it does not, the label prints no `{batch_no}`, `{expiry_date}` or
   `{manufacturing_date}`: the sale books the till's own lot (a fractional quantity takes the engine's pick), which
   may not be the one chosen on the sheet.
5. The weight is **typed**, in every frame, so the right to print a scale label is the right to type a sale's weight
   (*manual-weight*). Reading the counter's scale from the label sheet is a separate piece of work: the label
   sheet does not reuse the scale read of the weigh screen, and a clerk with a scale but without that right
   cannot print one until it does.

⚠ **Why some labels are refused today.** The engine's encoder writes the Price and Quantity segments from a
number it has not rounded, so about one price in eleven (9,175 of the 99,999 prices 0.01 to 999.99 at a factor of 100)
and about one weight in fifty-five (360 of 19,999 grams) is written wrong. The read-back refuses every one of
those and prints every other. The refusals end by themselves the day the engine rounds before it encodes (an engine fix is
requested); nothing here is removed then.

⚠ **Bounds, stated.** The read-back judges the till's PREVIEW of the scan: a legacy item Pricing Rule the label's
price still qualifies for is applied by the save and not shown there (a limit the till's own preview already has; none is
enabled on a served store and the engine refuses to save one), so such a label would book below its total. On a pack
under a kilo the till's unit rate is the total divided by the weight, so the receipt's *per unit* figure can differ
from the label's `{unit_price}` by a cent while the amounts agree. The read-back compares amounts at the site's
money precision. A label printed at one store carries that store's total and is read at another store's price on
a scan there. **Offline**, a till scans a label that carries a price at the price the label holds only while it is
connected: a weight-only label scans offline at the device's carried price, and a label with a price in its code
does not compose offline (the existing narrowing), so a deli till that drops its link refuses the labels it
printed. And it is true the day the label prints: a price changed or a mask edited later re-reads every scale
label already on the shelf, as it does without this feature. A Delimiter mask writes the number with its float
noise (`1998.9999999999998`) and the till reads it within a cent: the read-back judges the line the till books.

## 6. Offline

Labels are filled on the server, so the row is dimmed offline: *"Labels need a connection."*

⚠ **Scanned offline.** A till that has lost its link rings an item's barcode with no unit as the item's **stock**
unit, while a connected till rings it in the unit it sells the item in by default. So a label printed in a default
unit that is not the stock unit (a Pack-sold article whose only barcode has no unit) scans offline at one stock
unit's price, a known defect. A unit's own barcode (Item Barcode with that unit) scans the same online and
offline: give a pack-sold article a barcode for its pack.

## 7. Money and limits

The label prints a price; it never sets one, and its barcode carries none. The price is the till's, read
when the label prints: a label printed before a price change shows the old price, as any shelf label does,
while its barcode rings the till's price of the day. From a basket line the label still prints that price, never
the line's own (a markdown or a customer's price is that sale's, not the shelf's). The one exception is a scale
label for a weighed pre-pack (§5d), whose barcode DOES carry its weight and price: it prints only when the till's
own scan of it books exactly those, and what the cashier reads is the till's price of the day it printed.

⚠ The device's print dialog reports neither a print nor a cancel, so the till says *Handed to this device*,
never *Printed*. Up to 100 labels at a time.

## 8. Worked examples

**Size the stock to what you put on it.** `{barcode_svg}` always draws **16.4 mm tall** (10 mm of bars and the
digits under them) with about 1 mm of space under it, and as wide as its code needs, kept to the label's width;
it is never scaled. Each line of text adds about 4 mm at 9 pt and 5 mm at 12 pt. The label hides whatever runs
past its bottom edge, on paper and in the print-server PDF alike, so a layout that is too tall loses its last
lines without a warning. A 25 mm label holds the barcode and one line of text; a 30 mm label holds the barcode
and three, as in the example below. Keep a long item name to one line with `white-space:nowrap;overflow:hidden`.

**A 50 × 30 mm shelf label.** Template:

```html
<div style="font:bold 9pt sans-serif;white-space:nowrap;overflow:hidden">{item_name}</div>
{barcode_svg}
<div style="font:bold 12pt sans-serif">{currency} {price}</div>
<div style="font:7pt sans-serif">Batch {batch_no} · Exp {expiry_date}</div>
```

For `WHEY-1KG` at AED 189.00, batch `B-2609` expiring 2027-03-31, the label reads its name, a Code-128 of its
barcode, `AED 189.00` and `Batch B-2609 · Exp 31-03-2027` (in the site's date format). On 50 × 25 mm stock,
keep the barcode and the price line only.

**A Zebra 50 × 25 mm label** (kind `zpl`):

```
^XA^CI28
^FO20,20^A0N,28,28^FD{item_name}^FS
^FO20,60^A0N,40,40^FD{currency} {price}^FS
^FO20,110^BCN,60,Y,N,N^FD{barcode}^FS
^XZ
```

**A pharmacy's dispensing label, 50 × 30 mm** (a strip sold from a box). The shop adds two Data fields to
Item, `custom_strength` and `custom_route`, and an active Transaction Item Attribute named `Dose`; the cashier
types the dose on the basket line (*Item details*) and prints the label from that line:

```html
<div style="font:bold 9pt sans-serif;white-space:nowrap;overflow:hidden">{item_name} {item.custom_strength}</div>
<div style="font:8pt sans-serif">{item.custom_route} · {detail.Dose}</div>
<div style="font:7pt sans-serif">{uom} · Batch {batch_no} · Exp {expiry_date}</div>
<div style="font:7pt sans-serif">{store}</div>
```

It reads, for example, `Paracetamol 500 mg` · `Oral · 1 tablet three times a day` · `Strip · Batch P-2611 · Exp
30-06-2027` and the store's name. It carries no barcode, so a strip with no barcode of its own prints.

**A sheet of three across.** Labels per row 3 and 38 × 21 mm, with the code printed as text (a 21 mm label
has no room for the 16.4 mm Code-128 and two lines):

```html
<b>{item_code}</b> {uom}<br>{currency} {price}<br>{barcode}
```

7 labels print as three rows of three, three and one.

## 9. Telling an AI assistant

> Write an iVendNext POS label layout, version 1 (kind `html`, or `zpl` for a counter's Zebra printer: `^XA` … `^XZ`,
> the barcode drawn by the printer over {barcode}, never {barcode_svg}): one Retail Label Layout record, shaped by
> `label_layout.v1.schema.json` (`$defs/declaration`); the samples under `samples/label_layout/` are
> known-good and known-bad records. The template is HTML with only these placeholders: {item_code}
> {item_name} {barcode} {barcode_svg} {price} {currency} {uom} {batch_no} {expiry_date}
> {manufacturing_date} {weight} {unit_price} {store}, plus up to three of the item's own fields as
> {item.<fieldname>} (Data, Select, Int or Check, stored on the item and open to every role — never a money field)
> and one basket-line
> detail as {detail.<attribute>} (an active Transaction Item Attribute) — never Jinja, never a script, frame, form or event handler, and no other `{…}`
> (style with attributes, not a `<style>` block). Sizes are in millimetres, 10 to 150. {barcode_svg} draws 16.4 mm
> tall and is never scaled, and the label hides whatever runs past its bottom edge: make the stock tall enough for
> the barcode plus about 4 mm per 9 pt line and 5 mm per 12 pt line (a 25 mm label holds the barcode and one line).
