# S39 — Pharmacy counter rules (a check before payment and document checks)

A pharmacy sells medicine under a licence. A prescription line is paid only against a valid prescription for this customer. A controlled or prescription-only line is sold only by a pharmacist whose licence is in date. A controlled sale needs the patient's identity. Quantity caps hold, and dispensed medicine is not taken back. The same rules hold when a sale is made on the Desk.

The app checks these at **Pay** on the till, at a return's confirm, and when a sales order, delivery or sales invoice is submitted on the Desk. Each rule is a record the retailer fills: its drug schedules, its pharmacists, the prescriptions its pharmacist enters and its patients' records. Nothing is written in per country.

Where the pharmacist rings the prescription and a counter assistant takes the money at the dispensary's cash till, the pharmacist presses Pay (the check reserves the fill) and sends the sale to that till. Whoever rings it up there pays it in one press: the app judges the sale on the pharmacist who sent it, for no more than they sent, and the dispensing names both. A sent sale the cashier voids at the cash till after pressing Pay gives its fill back at once; one voided before, or from Held sales, keeps it until the pharmacist's POS day closes or the pharmacist in charge releases it.

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

**Sale details in the shop's words:** the till shows a sale detail by its name (*PP RXC Rx Number*). On the dispensary's till theme, in POS Studio's **Fields** tab, relabel the five on the *Sale details* screen: *Prescription number*, *Prescriber*, *Prescriber's licence*, *Directions*, *Prescription date*. Hide *Prescriber*, *Prescriber's licence* and *Directions* where the pharmacists never type over what the prescription says: the check reads them from the prescription. Keep *Prescription date* shown: the check fills it.

The label carries what Abu Dhabi, Dubai and Saudi Arabia ask of a part pack (the lot, expiry and storage). For the label: before installing, the line detail **Dose** (a Transaction Item Attribute, active), or the install stops; *Print* on Retail Label Layout for the dispensary's roles; each medicine's *Strength*, *Route* and *Storage*. For the erasure: *Keep a patient's records for (years)* in *PP RXC Settings*, the longest period its pharmacy law sets for a prescription or a register, and who gets **PP RXC Records Officer**; afterwards a System Manager deletes the copies the Desk keeps in *Deleted Documents*.

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
- As the pharmacist, press Pay and send the sale to the cash till; sign in there as a cashier who is not a pharmacist, ring it up from Held sales and pay it.
- Close the till day when you are done.

## Versions

### 1.1.1

- Its manifest is now 0.1.5. A sale the pharmacist sent to a cash till is paid there by whoever rings it up: the check judges it on the pharmacist who sent it, for no more than they sent, takes over its reserved fill, and the dispensing names both (*Sold by* the cashier, *Pharmacist* the one who sent it). Voided there after Pay, its fill comes back at once.
- A cashier refused a pharmacist-only line reads what to do (*Ask a pharmacist to ring it up; they can send it to this till.*), and a fill an unpaid sale holds says who frees it if that sale was voided. A walk-in sale paid this way is recorded under the walk-in customer, with no patient data.
- **Updating to 0.1.5:** move the service first (it answers a 0.1.4 shop as before). The update adds one field to the dispensing and asks nothing new.

### 1.1.0

- Its manifest is now 0.1.4: the dispensary's check fills the prescription's date, the dispensing label, and the erasure after the keeping period.
- **Updating to 0.1.4:** move the service first (it still answers 0.1.3's tills as before). Make the line detail *Dose*, then update. The update names the dispensary check's new address, the two new buttons and the app's user's new right to delete a patient's prescriptions, dispensings and record, and asks one consent; every check you had switched on stays on. A check you had switched off stays off, and one whose consent you had withdrawn waits for a System Manager's consent (the dispensary's refuses every sale until then).

### 1.0.0

- First version in the kit: prescription, pharmacist and patient rules at Pay and at Desk submit, each fill reserved in the retailer's own records.
- Its manifest is now 0.1.3: the patient's data and consent, the patient's own record, and the prescription's date on the sale with a prescriptions register.
- Each setting in app.json says its purpose (the line the Settings screen shows), whether it is required, and which settings go with it.
