# S52 — Phone plans from a telecom company (`pp_tel`), sold with the phone

A phone retailer sells mobile plans from a telecom company at its tills, each retailer with its own account with the telecom company. The cashier scans the phone and presses **Plans** to see the plans that fit it, with their prices. The cashier adds the chosen plan as its own item, priced from the retailer's price list, which your service keeps in step with the telecom company's prices. At Pay the check confirms the plan with the telecom company, and after payment the plan is activated and its number written back to a row under the sale.

**Industries:** Electronics and phones

**When to use it:** any link between the till and an outside system that prices something per retailer account (the outside system confirming each customer at Pay) and must hear about the sale afterwards: a telecom company's plans, an insurer's device cover, a utility's connection. Chapter 1c of the guide walks this sample hop by hop ([How the data travels](../../guide/01c_how_the_data_travels.md)).

## Start from it

```bash
ivn new acme_plans --from s52
```

## What to change

What a partner usually changes:

- **The telecom company's calls:** `service/telecom.py`, the file you change for a real telecom company (plans, offers, activations).
- **The rules:** `service/plans.py` (the Plans message, the check's verdict, the activation work and the price changes).
- **The settings record:** `PP TEL Settings` in `manifest.json` (`telecom_account`, `telecom_key`, `plan_item_group`, `price_list`, `walk_in_customers`).
- **The activation record:** `PP TEL Activation` in `manifest.json`.
- **The stand-in telecom company:** `standin/telecom_api.py` and `standin/accounts.json`, to run the whole flow with no network.
- **The app's id:** `IVN_LIBRARY_APP` in `app.json`.

More: the [recipe](../../recipes/point_handler.md).

**The customer sets:** its own telecom account and key in the `Default` record of *PP TEL Settings*, the item group the plans are in (one item for each plan, the telecom company's plan code as its item code), and the price list the plans are sold from.

## Run it

```bash
ivn check
ivn try
```

To run the whole flow with no network, start the stand-in telecom company:

```bash
python3 standin/telecom_api.py
```

## Try it at the till

- Scan a phone and press Plans; the till lists its plans.
- Add a plan as its own line and press Pay; the till confirms it with the telecom company.
- Close the till day when you are done.

## Versions

### 0.1.0

- First version in the kit: a telecom company's plans sold with the phone, priced, checked at Pay and activated after payment.
- Each setting in app.json says its purpose (the line the Settings screen shows), whether it is required, and which settings go with it.
- A cut-short answer from a retailer's site is handled as an unknown outcome, like a site that cannot be reached, never a crash.
