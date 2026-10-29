# Repairs by serial number — the recipe

An electronics or phone store repairs and services the units it sells, and each unit has a serial number (or an IMEI). This recipe gives the retailer the **repair** as its own record in iVendNext Desk, kept against the unit's serial: the fault, the condition at intake, the tests and their results, the work and the parts fitted, from the counter to the hand-over, with a slip for the customer. Every repair shows under its serial number, so the unit's **service history** is one list. It also shows how a store runs a **recall by serial** with what iVendNext already has, with no app. It is for an iVendNext Partner, or the CitiXsys Consulting Team, who wants a store's repair jobs off paper without code inside the retailer's iVendNext.

**Reference implementation:** `samples/s58_repairs_by_serial/`.

**When to use it.** The store takes units in for repair or service, tracks them by serial number, and keeps no record of what was done to each, or keeps it on paper. The serial numbers, their warranty dates, the stock and the sales are already the engine's: the parts leave stock with a Stock Entry of type **Material Issue**, and the till charges the repair as a service item.

**The four rules, here.** No code runs inside the retailer's iVendNext. No address is called: the app is a manifest of records, a workflow, a lock, a print format, a report and one field on Stock Entry. It reads and writes no money and no stock. Its only message to a customer is the retailer's own Notification, which sends through the retailer's own SMS or mail settings.

## What the store sees

1. **At the repair counter.** Store staff open **PP RPR Repair** in Desk and press **+ Add**. They choose the **Serial number**: its **Item**, **Item name** and **Warranty until** show, read only. They choose the **Customer** (blank for a unit of the store's own stock): its **Customer name** and **Customer's phone** show, read only. **Kind of job** (*Repair*, *Service*, *Test only*, *Recall work*), **Taken in at** (the store), **Received on** (today), **Ready by** (the date promised), the **Fault reported** and the unit's **Condition and accessories**. Saved, it is numbered `RPR-00001` and is **Received**; its slip prints for the customer, with a tag for the unit.
2. **The work.** **Start work**: **In repair**. A row per **Test** (its **Result** and a reading), the **Work done**, the **Technician** and a row per **Part fitted** (the part's item, what it is, its own serial number, how many). The Material Issue that takes the parts out of stock names the repair in its **Repair** field.
3. **Ready.** **Ready**: **Ready to collect**; the slip now shows the work, the tests and the parts. **Back to work** if the customer is not happy.
4. **The hand-over.** **Hand over**: **Collected**. From now on the repair's unit, customer, fault, condition, tests, work, parts and dates cannot change.
5. **A repair that will not go ahead.** **Cancel**: by store staff while the repair is **Received**, by a store manager once it is **In repair**. A cancelled repair keeps its number; the store never deletes one.
6. **The history and the queue.** The serial number's form lists its **Repairs**. The report **PP RPR Open repairs** lists the repairs not yet collected, by the date promised.

## Repairs

The record type `PP RPR Repair`, numbered `format:RPR-{#####}`, tracked (its history shows who changed it and when), its title the serial number:

| Field | What |
|---|---|
| `serial_no` | **Serial number**, a Link to Serial No; required |
| `item_code`, `item_name`, `warranty_until` | read only, `fetch_from` the serial's `item_code`, `item_name` and `warranty_expiry_date` |
| `kind` | **Kind of job**: Repair (the default), Service, Test only, Recall work |
| `customer` | the customer whose unit it is; optional |
| `customer_name`, `customer_phone` | read only, `fetch_from` the customer's `customer_name` and `custom_phone_no` (the field the till's new-customer sheet and customer edit write) |
| `store` | **Taken in at**, a Warehouse; required |
| `received_on`, `ready_by` | **Received on** (today by default; required) and **Ready by** |
| `fault`, `condition` | **Fault reported** (required) and **Condition and accessories**, text |
| `tests` | child table `PP RPR Test`: `test`, `result` (blank, Passed, Failed, Not run), `reading` |
| `work_done`, `technician` | text |
| `parts` | child table `PP RPR Part`: `item` (a Link to Item), `part` (what it is), `part_serial` (the part's own serial, typed), `quantity` (a whole number, 1 by default) |
| `sale` | **Paid by sale**, a Link to POS Invoice |
| `collected_by`, `notes` | text; the notes are never printed |

**Sales User** and **Sales Manager** read, write, create and print repairs; only **System Manager** deletes one; **Stock User** reads them, so the Stock Entry's **Repair** field can find one. A repair shows under the Serial No, the Customer and the POS Invoice it names (manifest `links`).

**Reading the serial.** Sales User holds no right on Serial No, so the retailer gives Sales User (and Sales Manager) **Read** on Serial No in the Role Permissions Manager (a new rule comes with *Read* and *Select* ticked). *Select* alone is not enough: the search finds the serial, but when it is picked the form fetches the item and warranty date with the person's own rights and says *You need Read permission to fetch values* (the save itself fills them either way, with no right needed). *Read* also opens the serial's own form, with its repairs, to the counter.

## The workflow and the lock

| State | Who edits |
|---|---|
| Received | Sales User |
| In repair | Sales User |
| Ready to collect | Sales User |
| Collected | Sales User |
| Cancelled | System Manager |

The actions: **Start work** (Received to In repair), **Ready** (In repair to Ready to collect), **Back to work** (Ready to collect to In repair), **Hand over** (Ready to collect to Collected), each by Sales User; **Cancel** (Received to Cancelled, Sales User; In repair to Cancelled, Sales Manager). Nothing leaves *Collected* or *Cancelled*.

A **save rule** of kind `locked_in_state` (`save_rules`) refuses any change to `serial_no`, `kind`, `customer`, `store`, `received_on`, `ready_by`, `fault`, `condition`, the `tests` rows, `work_done`, `technician` and the `parts` rows once the repair was saved **Collected** or **Cancelled** (the save that moves it there may still change them), at every save: Desk's form, an import and the record API alike, with the message *"This repair is closed: its unit, customer, fault, tests, work and parts stay as they were. Take a new repair for the serial instead."* (A workflow's *who edits* and a read-only field are only the browser's rules; the lock is the save's.) The fetched copies are not locked: each is fetched again at each save, so a lock on one would refuse every later save after its source changes. Nor is `sale`: a till sale cancelled later leaves a link the framework refuses at every save, and a locked link could then never be cleared.

## The slip

The print format *PP RPR Repair slip* (Jinja) reads only the repair's own fields and its rows, under the store's default **Letter Head**: a Jinja print places the letter head itself, `{% if letter_head and not no_letterhead %}<div class="letter-head">{{ letter_head }}</div>{% endif %}` at its top (only Desk's standard layout adds it on its own). It prints the kind and number (*Repair · RPR-00001*), the item, the serial and its warranty date, the customer, the store, the day and the date promised, the fault and the condition. It reads the repair's step (`workflow_state`), never a tick box: the API can set a read-only box, and Desk's Duplicate copies one, but never the step (the workflow's own field is `no_copy`). While the repair is not yet ready it says *Please bring this slip when you collect*; once it is **Ready to collect** or **Collected** it prints the work done, a row for each test that has a name, and a row for each part with an item or a description, with the part's serial (a blank row is skipped). A cancelled repair prints *Cancelled: this repair was not done.* at the top. At the foot, a **unit tag**: the repair's number in large type, the serial and the customer, to cut off and keep with the unit. The print tests the step's end (`state.endswith(" Collected")`), so a renamed prefix still matches.

## Steps

1. **Add the record types above** to your manifest (`doctypes`, the two tables with `"istable": 1`), with no money field: the till charges the repair. Never make a table `reqd`: Desk drops a row whose list fields are all blank, so *no tests yet* is a repair with no rows.
2. **Add the workflow** (`workflows`), its states and actions under your prefix, with no `update_field`: what reads the repair reads the step.
3. **Add the lock** (`save_rules`, kind `locked_in_state`, mode `refuse`), naming the closed states and every field the slip prints except the fetched copies. A lock needs an active workflow on its record type, and installs switched off: the retailer switches it on. It judges the state the record was saved in, so never lock a field the move into a closed state writes.
4. **Tell the customer the unit is ready, with the retailer's own Notification** (a manifest notifies only the retailer's own users). In Desk, **Notification**, **+ Add**: Document Type *PP RPR Repair*, Send Alert On **Value Change**, Value Changed **Workflow State**, Condition `doc.workflow_state == "PP RPR Ready to collect" and doc.customer_phone` (your prefix in the state's name), the channel **SMS** to the document field **Customer's phone**. A refused send never fails the repair's save: it goes to the Error Log.
5. **Add the field on Stock Entry** (`custom_fields`): a Link to your repair, named with your reserved field prefix, `allow_on_submit` 1, `depends_on` the purpose *Material Issue*, never `reqd`. A Material Issue needs a **Stock Entry Type** of that purpose: a site set up without the setup wizard's records has none, and the retailer adds *Material Issue* once. Then the report (`reports`, Report Builder, filtered `workflow_state not in` your *Collected* and *Cancelled*, ordered by `ready_by asc`), the Connections (`links`, the repair under Serial No, Customer and POS Invoice) and a `documentation` property setter that points at your help.
6. **Check it before it reaches a retailer:** `python3 tools/check/check.py samples/s58_repairs_by_serial`.

## What the retailer does

1. **Install the app.** It adds the repair, its workflow and lock, the slip, the report, the Stock Entry field and the Connections. No setting, no role, no outside address.
2. **Switch the lock on:** Desk › *Retail Save Rule* › *PP RPR repair locked once collected* › **Enabled**. A manifest installs every save rule switched off; until it is on, a collected repair can still be changed.
3. **Give Sales User and Sales Manager *Read* on Serial No**, so the repair counter finds a serial and the form shows its item and warranty date.
4. **Give Sales User** to the people at the repair counter; a Sales Manager cancels a repair in work. Whoever takes parts out of stock holds Stock User; add the Stock Entry Type *Material Issue* if the site has none.
5. **Put the store's details on the Letter Head** the store prints with, and **add its own Notification** if it tells customers by SMS (step 4).

## Recall by serial, with what iVendNext already has

A maker recalls a model, or the units between two serial numbers. The store needs three things, and the engine has each:

1. **Who bought them.** Desk › *Stock* › **Serial No Ledger**: the recalled **Item** (its one required filter), and the **Serial No** of one recalled unit. Each row is one movement of the unit: its movement out by a sale (voucher type *Sales Invoice*) names its **Party**, the customer it was sold to. Look each unit up by its own serial: listed by the item alone, a sale line that carried several units names its voucher and buyer on the first unit's row only, the others beneath it with neither (the till rings one serial per line, but an order line handed over later, a Desk sale or a delivery may carry several). A till sale appears once its day's sales are booked to stock: at once on some sites, at the day's close on others. A walk-in sale names the store's walk-in customer, so there is no one to contact; a customer the till made keeps the phone in the customer's own record. **Stock User** opens the report (it is a report on the stock ledger: *Sales User* alone is refused it); it shows customers' names, so give it only to whoever runs the recall. For many serials, export the item's rows (**Menu › Export**), carry each sale's voucher and buyer down to the rows beneath it, and match the list.
2. **Stop the rest being sold.** Move the recalled units still in stock to a store no till sells from (a quarantine warehouse that is on no POS Profile) with a **Stock Entry** of type **Material Transfer** naming their serial numbers. A serial sells only from the till's own store, so the till then refuses them. An offline till learns of the move only when it next syncs: a recalled unit it sold meanwhile is refused then, and that sale stays held on the till until a manager settles it, so its buyer is in no report until then.
3. **The units brought back.** Take each in as a repair of kind **Recall work**; filter the repair list by **Kind of job** to see which have come back, and each serial's **Repairs** shows its own.

This is configuration, not an app: nothing to install for it. A recall by lot (a batch of food or medicine) is the sample S40's work.

## Limits

- **The repair is written in Desk**, at the repair counter; a till key that takes it in at the till is a version of your own.
- **The app holds no charge, quote or deposit:** the till charges the repair; a quote the customer approves first is a version of your own.
- ***Collected by*, *Paid by sale* and the notes stay editable after the hand-over:** the slip prints none of them (a cancelled repair is read only in Desk to store staff). **What is read from the serial and the customer follows them:** a slip reprinted after the customer is renamed prints the new name; the serial and the customer themselves cannot change.
- **Duplicating a Material Issue copies its Repair:** clear it on the copy (a manifest's field cannot carry `no_copy`).
- **The stock entry names the repair; the repair does not list its stock entries** (a manifest's link may only list its own records under a retailer's record). Filter the Stock Entry list by **Repair**.
- **A part's own serial is typed, not chosen:** a part tracked by serial in stock is named on the Material Issue as well.
- **Desk shows the states and buttons with the app's prefix** (*PP RPR Hand over*).
- **Before removing the app,** delete the retailer's own Notifications on the repair.
- **The customer's details are personal data** the retailer keeps under its own policy. Uninstalling removes the repairs and the Stock Entry field; the install's export keeps a copy.
