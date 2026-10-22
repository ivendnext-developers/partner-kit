# Call-centre orders by district: send each phone order to its store — the recipe

A retailer with a call centre takes orders by phone and ships each one from the store that serves the customer's district. The agent should enter the order once and not have to know which store that is. This recipe does it with the shop's own district tree and one button. The manager sets a **Serving store** on each district of the **Territory** tree. The agent presses **Send to store** on the draft order. Your service writes that store's warehouse on the order and on every line, and the store then sees the order in its own list. It is for an iVendNext Partner, or the CitiXsys Consulting Team, who wants orders routed by district without code inside the shop.

**Reference implementation:** `samples/s35_call_centre_orders/`.

**When to use it.** The routing table belongs to the shop (district → store) and the routing is the same every time, but the shop cannot do it alone: a manifest cannot fetch into the order's own warehouse field, a save rule writes only numbers, and the shop never copies the header's warehouse down to the lines. So a service writes it, and a Desk action is how a person asks for it. For a check that only refuses a wrong warehouse at submit, use a document check ([recipe](document_check.md)) instead; it never routes.

**The four rules, here.** No code runs inside the shop. One address is called, your service, and only when someone presses the button. The service changes only the warehouses on a draft order: it sets no price, never touches a submitted order, and never writes over an edit someone saved after it read the order. The shop's own save may re-rate the order at the new warehouse (a store's own tax): the agent is told.

## What the agent and the store see

1. The agent enters the order as today. Its **Territory** comes from the customer and can be changed for this order (a gift, a second address). The agent saves it.
2. The agent presses **Send to store** and confirms: *"Send this order to the store that serves its territory? Its warehouse changes on every line."*

   ![Send to store on a draft sales order on a demo shop, and its question](../samples/s35_call_centre_orders/screenshots/05_send_to_store.png)
3. *Sent to store — This order and its 2 lines now ship from Maadi Store, the store for Maadi.* The form reloads with the store in *Set Source Warehouse* and on every line. A district with no store of its own says which territory's store it took: *"…the store for Cairo, which Heliopolis is part of."*

   ![Sent to store on a demo shop: This order and its 2 lines now ship from Store 2, the store for Sandton](../samples/s35_call_centre_orders/screenshots/06_sent_to_store.png)
4. The agent submits the order. The store's staff find it in their Sales Order list, filtered on their own *Set Source Warehouse*. Its delivery note ships from their warehouse.

Pressed again, the button says *Already with its store* and changes nothing.

## Steps

1. **Add the Serving store to Territory** (a link to Warehouse, shown in the Territory list and as a filter):

   ```json
   "custom_fields": [
     {"dt": "Territory", "fieldname": "pp_cco_store", "fieldtype": "Link", "options": "Warehouse", "label": "Serving store",
      "insert_after": "parent_territory", "in_list_view": 1, "in_standard_filter": 1,
      "description": "The store whose warehouse ships call-centre orders for customers in this territory. Leave it empty to use the store of the territory above."}]
   ```

2. **Add the button on a draft Sales Order's form**, for the roles that take orders, sending only the order's name and territory (your service reads the rest itself), and the service that answers it ([Desk action recipe](desk_action.md)):

   ```json
   "extension_subscriptions": [
     {"key": "route", "point": "desk_action", "label": "Send to store service",
      "endpoint_url": "https://your-service.example/press/route", "timeout_seconds": 10}],
   "desk_actions": [
     {"record_type": "Sales Order", "label": "Send to store", "placement": "form", "service": "route",
      "roles": ["Sales User", "Sales Manager"], "on_draft": 1, "on_submitted": 0, "send_fields": "name, territory",
      "confirm_text": "Send this order to the store that serves its territory? Its warehouse changes on every line."}]
   ```

3. **Add a feed registration** for the app's user (it follows Sales Order; leave it switched off (it installs off): switched on, it would record every sales order's saves for the app's user). A service that serves many shops receives the user's key through it on *Connect again* (guide chapter 14b):

   ```json
   "registered_applications": [
     {"name": "PP CCO Routing feed", "description": "the routing service reads and writes sales orders as this feed's user",
      "events": ["Sales Order"]}]
   ```

4. **Write the service** (`samples/s35_call_centre_orders/route.py` and `service/app.py`, standard library). For each press:
   - check the signature (the subscription's secret);
   - read the order with the app's user (`GET /api/resource/Sales Order/<name>`); answer in words if it is submitted or has no territory;
   - walk the territory up the tree (`GET /api/resource/Territory/<name>`, `parent_territory`) to the first Serving store;
   - read that warehouse and refuse in words a group, a disabled one or another company's (the shop saves a draft with any of these and refuses it only at submit);
   - if the order already ships from that store, answer *Already with its store* and write nothing;
   - otherwise write `{"set_warehouse": store, "items": [every line as read, its warehouse changed], "modified": <as read>}` with `PUT /api/resource/Sales Order/<name>` (every line, a supplier-delivered one too: the shop clears the header when the lines differ; and a bundle's parts, `packed_items`, whose warehouse the shop fills only when it is empty), compare the saved totals with the totals as read, then answer `{"refresh": true, "message": …}`, saying the new total if it moved;
   - a stale write (HTTP 417 `TimestampMismatchError`): read once more, answer *Already* if routed, else ask the agent to reload; never retry the write; any other 417: *The shop would not save this order*, never the shop's own text.

5. **Check it before the shop:** `python3 tools/check/check.py samples/s35_call_centre_orders` (the shop's checker and its install's two extra refusals).

## What the shop does

1. **Install the app.** The service and the button come in switched off. The install adds the Serving store field and makes no role.
2. **Give the app a user**, as in the [integration user recipe](integration_user.md): tick **Is Desk User**, set no password and no User Permissions, and generate its API key. In **Role Permissions**, give a role of the shop's own these rights, and give the user that role alone:

   | Record type | Right | Why |
   |---|---|---|
   | Sales Order | Read, Write | the service reads the order and writes its warehouses |
   | Territory | Read | the walk up the district tree |
   | Customer | Read | the order's own save reads its customer with a rights check |
   | Warehouse | Read | the store is checked before the write |

   The role reaches every sales order (read and write) and every customer, territory and warehouse (read): give it to the app's user and no one else. *Sales User* also works, but it reaches further than the app uses: it creates and submits orders.
3. **Choose the user** as the *Application User* of the feed *PP CCO Routing feed*. A hosted service: press **Connect again** on the app.
4. **Switch the service on** in **Retail Extension Subscription** (*Send to store service*: read what it is sent, tick the consent), then the button in **Retail Desk Action** (*Send to store*).
5. **Set a Serving store on the districts** (a Sales Master Manager): a store warehouse of the same company, never a group. A governorate's store serves its districts that have none.

   ![The district Sandton on a demo shop, with Store 2 as its Serving store](../samples/s35_call_centre_orders/screenshots/04_serving_store.png)
6. **Each store saves its list once**: the Sales Order list filtered on its own *Set Source Warehouse*.

   ![The Sales Order list filtered on Store 2's Set Source Warehouse, on a demo shop](../samples/s35_call_centre_orders/screenshots/08_store_list.png)

   With a User Permission on its own warehouse, a store's staff see the orders sent to their store and not those sent to another; an order whose Set Source Warehouse is empty (none set, or lines on different warehouses) is seen by every store.

## Limits

- **The territory is the customer's.** An order for another district needs its territory changed before the press.
- **The order must be saved first:** the shop reads the saved order, never the form's copy.
- **Only drafts.** To send a submitted order elsewhere, cancel and amend it.
- **No notice to the store.** The store's filtered list is its inbox.
- **One order at a time:** the button is on the form only.
- **Removing the app removes the Serving stores** with the field (the uninstall's export keeps a copy).

## Technical notes

### What the service sends and writes

- **Each press sends** the order's name and territory, the pressing user (an e-mail address) and the language. The consent the System Manager reads lists exactly these.
- **The service reads** the whole order (customer, addresses, lines, quantities and prices), the territories up the tree and the store's warehouse, **and writes the order back**. A table is replaced whole on a write, so every line goes back as read with only its warehouse changed. The shop never copies the header's warehouse down to the lines (it only clears the header when the lines differ), so the service writes both.
- **What moves besides the warehouses:** each line's stock figures, and its cost at the new warehouse (`valuation_rate`) and the profit worked out from it (`gross_profit`), as when someone changes the warehouse in Desk. On our bench's untaxed order the price, the amounts and every total stayed as they were. The service sets no price, but the shop's own save works the order out again at the new warehouse: a store's own item tax, or a price limited to a warehouse, can change the total, and the answer then says so (*Its total is now … (was …)*).
- **An edit saved meanwhile is never overwritten:** the write carries the order's `modified` as read, and the shop refuses a stale one (`TimestampMismatchError`, HTTP 417). The service reads the order once more without writing: *Already with its store* if a second press routed it meanwhile, otherwise it asks the agent to reload. It never retries the write, so a warehouse a person chose meanwhile stands.
- **The shop's own words never reach the agent.** The service branches on the error's type (`exc_type`), never shows its message, and answers in its own sentences.
- **A repeated press is harmless.** The routing is the same every time, so a second press, a retry or two copies of a hosted function find the order routed and write nothing. Two writes racing on one order are settled by the shop's `modified` check.

### What was proven where

- **Laptop:** `samples/s35_call_centre_orders/tests/` (45 tests: the store, the store above, a second press, no store, no territory, a submitted order, an edit in between, a group, disabled or other company's store, a bundle's parts, a changed total, a double press, an order the shop will not save, a refused user, many shops, the function entry, the contract) and `tests/canaries.py` (28 mutations, each turns its test RED).
- **Our test bench** (2026-10-21, iVendNext POS app at beta's build): the manifest installed switched off. The app's user held a shop role with exactly the rights above. A Sales User's presses went through the button's own call: the Maadi order went to Maadi's store, a Heliopolis order to Cairo's, and an order with a supplier-delivered line to Maadi's on every line (a second press: *Already with its store*). A product bundle's part moved to Maadi's warehouse with its line. A draft stored with a wrong total came back *Its total is now 250.46 (was 999.0)*: the shop's save works the order out again and the service says so. Every field of the order and its lines was compared before and after, and only the fields above moved; the totals were equal. A second press wrote nothing. A district with no store, and a group warehouse, were refused in words. A submitted order and a user without a Sales role were refused before the service was called. A stale write was refused by the shop, and the press after the edit kept it. Maadi's Stock User saw the Maadi order and not Cairo's, and saw an order whose Set Source Warehouse was empty too; the routed order's delivery note took Maadi's warehouse. An order the shop would not save was answered in the service's own words. The feed recorded nothing. In a real browser, the agent pressed the button and the form reloaded with Cairo's store; the manager set a Serving store on Territory; the store user opened the filtered list. The uninstall left the site as found.
- **A demo shop, from its App library** (2026-10-22, the hosted service at `call-centre-orders.ivendnext.app`): *Get a free key*, the install, the app's user with the four rights above, *Connect again* (the service received the user's key), the service's consent, the button switched on, a Serving store set on a district in a browser. As a Sales User, *Send to store* sent a Sandton order to Sandton's store on both lines (1.5 s), a second press said *Already with its store*, and a Soweto order took the store of Gauteng, *"which Soweto is part of"*. The store's filtered list showed its order.
- **Measured, not assumed:** with read on Sales Order and Territory alone the shop refused the write (*"does not have doctype access via role permission for document Customer"*); with read on Customer it passed. The shop saved a draft whose lines named a group warehouse, which is why the service checks the store first.
