# S21 — Field rules for one till theme

The retailer's own words and fields on one till theme, with no code: the sale's line reads *Product*, the customer's card says *Stars*, the new-customer sheet has no email field, and a new customer needs a phone. Data only.

![The sale's line heading reads Product](screenshots/01_the_line_heading_reads_product.png)

**Industries:** every industry

## Start from it

```bash
ivn new acme_field_rules --from s21
```

## What to change

What a partner usually changes:

- **The theme:** `theme` on each rule in `manifest.json`. The sample names `PP Partner Till`; use the customer's own till theme, or **Check** refuses the rule.
- **The words:** `label` on the `relabel` rules (`cart_line` · `item_name`, `customer_card` · `points`).
- **What the new-customer sheet shows and asks for:** the `hide` rule on `email` and the `require` rule on `phone`, `surface` `customer_create`.

A rule changes what the till shows and asks for, never what it charges.

More: the [recipe](../../recipes/field_rules.md).

**The customer sets:** the till theme the rules belong to. If it does not exist yet, make it in POS Studio: open a theme, press **Save as a new theme**, name it and save.

## Run it

```bash
ivn check
ivn try
```

## Try it at the till

- Start a till that wears the app's till theme: the sale's line reads Product and the customer's card says Stars.
- Add a new customer with no phone; the till asks for one.
- Close the till day when you are done.

## Versions

### 0.1.0

- First version in the kit: field rules for one till theme.
- The README says its till theme PP Partner Till must exist before you install, and how to make it.
