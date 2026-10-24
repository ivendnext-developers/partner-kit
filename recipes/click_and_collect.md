# Click and collect: a Desk board of web orders — the recipe

A store that sells on the web and lets its customers collect in store needs two lists: the web orders it still has to pick, and the orders waiting for their customer. And when the customer comes, someone records the hand-over. This recipe gives every store those lists and that record from a manifest alone: a Report Builder report, a workspace, and two fields on the delivery note, one of which filters the Delivery Note list into the waiting list. It is for an iVendNext Partner, or the CitiXsys Consulting Team, who wants the same board in every store without a screen of its own.

**Reference implementation:** `samples/s33_click_and_collect/`.

**When to use it.** Configuration first: a retailer could make the same fields with Customize Form and the same reports with Report Builder. A manifest is for shipping it to many retailers the same way, and for removing it in one step.

**The four rules, here.** Nothing is called and nothing leaves the retailer's iVendNext. The fields record a hand-over; they change no money, no stock and no order.

## Steps

1. **Add the two fields to Delivery Note**, both settable after the note is submitted (`allow_on_submit`), with no default (the checker refuses a default on a retailer's own record type):

   ```json
   "custom_fields": [
     {"dt": "Delivery Note", "fieldname": "pp_ccb_handed_over", "fieldtype": "Check", "label": "Handed over",
      "insert_after": "po_no", "allow_on_submit": 1, "in_list_view": 1, "in_standard_filter": 1},
     {"dt": "Delivery Note", "fieldname": "pp_ccb_collected_by", "fieldtype": "Data", "label": "Collected by",
      "insert_after": "pp_ccb_handed_over", "allow_on_submit": 1}]
   ```

2. **Add the pick list** (Report Builder only: its filters are data). A web order is an order with a customer's order number (`po_no`), which our WooCommerce connector fills with the web order's number:

   ```json
   "reports": [
     {"name": "PP CCB Web Orders To Pick", "ref_doctype": "Sales Order", "report_type": "Report Builder",
      "columns": ["name", "customer_name", "set_warehouse", "delivery_date", "po_no", "status"],
      "filters": [["docstatus", "=", 1], ["status", "in", ["To Deliver and Bill", "To Deliver"]], ["po_no", "is", "set"]],
      "order_by": "delivery_date asc"}]
   ```

   It names the store's warehouse (`set_warehouse`), so a store filters its own. ⚠ On today's iVendNext it does not apply a manifest report's `columns`: the report opens with the record type's usual list columns, and the store adds the others from the column settings (asked of the product).

   ![The report Web orders to pick on a demo store, one web order to pick](../samples/s33_click_and_collect/screenshots/02_web_orders_to_pick.png)

   ⚠ **Not a report for the waiting list.** A report on Delivery Note filtered on `pp_ccb_handed_over` looks right, but iVendNext refuses it: its install checks a report's columns and filters (and a card's or chart's field) against the record type as it is before the install, so a field the same manifest adds is *not a field* yet. `tools/check/check.py` and `tools/deploy/deploy.py` refuse it too (`tools/manifest/site_rules.py`). The waiting list is the Delivery Note list itself, where *Handed over* is a list column and a standard filter (`in_list_view`, `in_standard_filter`).

3. **Add the workspace**: a header, a line naming the report and the waiting list's filter, and shortcuts to the **Sales Order** and **Delivery Note** lists. ⚠ Not a shortcut to the report: iVendNext makes a workspace before the manifest's own reports, so that link cannot be saved, and `site_rules.py` refuses it.

   ![The Click and collect workspace on a demo store: its line and the two lists](../samples/s33_click_and_collect/screenshots/01_workspace.png)

4. **Check it:** `python3 tools/check/check.py samples/s33_click_and_collect`, and the sample's tests.

## What the store does

1. Picks a web order the usual way: from its sales order, it makes and submits the delivery note. A WooCommerce web store then tells the customer *Ready to collect* (the connector does that, not this app). The order leaves **Web orders to pick**, and its note shows in the Delivery Note list filtered on **Status** To Bill or Completed, **Is Return** No, **% Returned** less than 100, **Handed over** No, **Customer's Purchase Order No** is set, **Set Source Warehouse** your store's warehouse, and **Date** on or after the install day (each person who hands orders over saves that filter once as *Waiting for collection*: a saved list filter is the user's own).

   ![The Delivery Note list's Filter panel with the waiting list's seven conditions, each added under + Add a Filter](../samples/s33_click_and_collect/screenshots/03_waiting_filter.png)

2. When the customer comes, it opens the note, and on its **More Info** tab under **Customer PO Details** ticks **Handed over**, writes **Collected by** and saves. The note leaves the list, and its history (*Activity*) records who ticked it and when.

   ![A delivery note's Customer PO Details: the web order number, Handed over ticked, Collected by filled in](../samples/s33_click_and_collect/screenshots/04_handed_over.png)

   ![The note's Activity line naming the change](../samples/s33_click_and_collect/screenshots/05_handed_over_history.png)

## Limits

- The lists are in Desk. The till's own pickup board lists till sales only, and a page on the till opens only over a sale, so these lists are not on the till.
- A Desk order typed with a customer's order number shows too, and so does a web order shipped from a store's warehouse (tick **Handed over** when the carrier takes it).
- A web order booked as a sales invoice has no sales order to pick: it appears once its delivery note exists.
- Who and when are the note's history, not fields.
- On today's iVendNext a delivery-note return does not update its original's % Returned (measured on our test bench), so an order returned before it is collected stays on the list: cancel its delivery note instead of returning it.
- **Notes from before the install** carry *Handed over* No, so a store's older web deliveries would wait too: add **Date** on or after the day you install to the saved filter.
- **A return or an amended note copies** *Handed over* and *Collected by* from its original (a manifest cannot mark them not-to-copy); the waiting filter leaves returns out, and an amended note's fields can be cleared by hand.
- Removing the app removes the two fields and their values (its export keeps a copy, in a private file); the delivery notes stay.

## Technical notes

Proven on our test bench on 2026-10-18: see the sample's README, *The bench*.
