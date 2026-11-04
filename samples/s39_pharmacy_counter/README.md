# S39 — Pharmacy counter rules (a check before payment and document checks)

A pharmacy sells medicine under a licence. A prescription line is paid only against a valid prescription for this customer. A controlled or prescription-only line is sold only by a pharmacist whose licence is in date. A controlled sale needs the patient's identity. Quantity caps hold, and dispensed medicine is not taken back. The same rules hold when a sale is made on the Desk.

The app checks these at **Pay** on the till, at a return's confirm, and when a sales order, delivery or sales invoice is submitted on the Desk. Each rule is a record the retailer fills: its drug schedules, its pharmacists, the prescriptions its pharmacist enters and its patients' records. Nothing is written in per country.

The dispensary's till fills the prescription's date at Pay, a dispensing label prints from the basket line, and after the keeping period the Records Officer lists the patients due and erases them on a *PP RXC Erasure*, which keeps who did it, when and under which period.

**Industries:** Pharmacy

## Start from it

```bash
ivn new acme_rx --from s39
```

## What to change

What a partner usually changes:

- **The market's schedules and their rules:** loaded as *PP RXC Drug Schedule* records, no code.
- **A rule:** a pharmacist's exception with a reason, a fixed price on medicine, an e-prescription link (`decide` in `rxrules.py`).
- **The words the cashier reads:** `rxrules.py`.
- **Your service's address:** every `host.docker.internal` address in `manifest.json` is the sample's test address; write your own.
- **The service's prefix:** `RXC_PREFIX`, in step with the app's name.

More: the [recipe](../../recipes/pharmacy_counter.md).

**The customer sets:** its drug schedules (one per class, each with its rules); who gets **PP RXC Pharmacist**, and the pharmacist in charge, who gets **PP RXC Pharmacist in Charge**, adds each pharmacist with their licence number and *valid until*, and enters the premises licence; and each patient's identity and consent on their *PP RXC Patient* record, entered on the Desk (the till cannot take them). Give the app's own user a plain read on Item, Item Group, Customer, POS Profile, POS Invoice, POS Opening Entry, Sales Order, Delivery Note and Sales Invoice.

The label carries what Abu Dhabi, Dubai and Saudi Arabia ask of a part pack (the lot, expiry and storage). For the label: before installing, the line detail **Dose** (a Transaction Item Attribute, active), or the install stops; *Print* on Retail Label Layout for the dispensary's roles; each medicine's *Strength*, *Route* and *Storage*. For the erasure: *Keep a patient's records for (years)* in *PP RXC Settings*, the longest period its pharmacy law sets, and who gets **PP RXC Records Officer**.

## Run it

Make the line detail **Dose** first, or the install stops.

```bash
ivn check
ivn try
```

## Try it at the till

- Sell a prescription medicine with no prescription number; the till stops it at Pay.
- Add the prescription number in Sale details and press Pay again: the prescription's date fills itself.
- Type the dose on the line and press Print label on it: the dispensing label prints in the line's unit.
- Close the till day when you are done.

## Versions

### 1.1.0

- Its manifest is now 0.1.4: the dispensary's check fills the prescription's date, the dispensing label, and the erasure after the keeping period.
- **Updating to 0.1.4:** move the service first (it still answers 0.1.3's tills as before). Make the line detail *Dose*, then update. The update names the dispensary check's new address, the two new buttons and the app's user's new right to delete a patient's prescriptions, dispensings and record, and asks one consent; every check you had switched on stays on. A check you had switched off stays off, and one whose consent you had withdrawn waits for a System Manager's consent (the dispensary's refuses every sale until then).

### 1.0.0

- First version in the kit: prescription, pharmacist and patient rules at Pay and at Desk submit, each fill reserved in the retailer's own records.
- Its manifest is now 0.1.3: the patient's data and consent, the patient's own record, and the prescription's date on the sale with a prescriptions register.
- Each setting in app.json says its purpose (the line the Settings screen shows), whether it is required, and which settings go with it.
