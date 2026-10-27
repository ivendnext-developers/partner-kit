# S26 — Derived price lists (a price list worked out from another, kept in step)

*Start from this sample: `python3 tools/manifest/start.py s26_derived_prices --prefix "ACME DPL"` copies it into `apps/` of your repository under your own prefix (your company's first word, then a short name for the app) and checks it ([how](../../recipes/make_it_your_own.md)).*

## What the retailer does

iVendNext keeps one price list worked out from another: the selling list is 1.5 times the buying list, or the wholesale list is 0.9 of the retail list. When someone changes a price on the source list, the app changes the derived price within seconds. Nothing changes at the till: the cashier sells at the list's price as before.

| What happens | When |
|---|---|
| The target list gets the item's price: source × factor + amount, rounded to the step at the retailer's decimal places, never below the floor | a price is saved on the source list, or a rule is added or its numbers change (every source price is worked out again) |
| Nothing is written | the target price is already right (an event repeated, or a save that changed nothing) |
| The target price is kept and listed as a person's price | someone set a price for that item on the target list that is still selling, or changed the app's price there after it was written |
| The target price is given an end date of yesterday (never deleted) | its source price was deleted, or made a price for one customer, supplier or batch |
| The made price moves with its source | the source price's item or unit was corrected |
| The next list down the chain follows too (A → B → C) | a rule's target is another rule's source |
| The rule is refused and listed | its lists are in two currencies, its step or floor is finer than its decimal places, another rule writes the same list, or the rules make a loop |

**Bounds, said plainly.**
- The new price arrives seconds after the source is saved (14 seconds on a sandbox; about a minute at worst when the retailer's background worker is busy, chapter 5); a sale in those seconds is priced at the old price. Tills take the new price at their next sync, and an offline till sells at the list it holds.
- Only prices for everyone are derived: a price for one customer, one supplier or one batch is left alone.
- A promotion or a member discount still applies on top, as always.
- Run one copy of the service per retailer: two at once can both write a new row before either sees the other's.
- A deleted source ends its rows from yesterday, by the service's clock.
- **A target list that already has prices keeps them.** Each is a person's price, held and listed. To hand a list to the rule, end or delete those prices first, or derive into a new list.
- The decimal places are the rule's own field: set it to the retailer's currency precision (iVendNext sizes every price from that system-wide setting).
- The floor wins over the step: a floor of 4.99 with a step of 1 gives 4.99 when the worked-out price is lower.
- **Switching a rule off, changing its target list, or uninstalling the app stops the following.** The prices it made stay at their last value, no longer followed or checked: end them, or hand the list to a person, at the same time.

## What the retailer does to set it up

1. Install `manifest.json` (the retailer's administrator, on the install screen; on your sandbox, `tools/deploy/deploy.py`). It adds `PP DPL Rule`, the feed registration *PP DPL Prices* (switched off) and the role **PP DPL Integration** (empty).
2. In **Role Permissions**, give PP DPL Integration **read** on Price List, and **read, create and write** on Item Price. A manifest grants rights only on its own record types ([the integration user recipe](../../recipes/integration_user.md)). ⚠ With these rights the key can change **any** item price in the retailer's iVendNext: give the role to this app's user alone.
3. Make the app's integration user with that role and generate its API key.
4. Choose that user on the feed registration *PP DPL Prices* and tick **Item Price**.
5. Run the service with the user's key (below).
6. Add a **PP DPL Rule**: a short name, the source and target price lists, the factor, an amount to add, the rounding step and direction, the floor, the decimal places; tick **Enabled**. The next pass writes every target price that no person has set.

**What leaves the retailer's iVendNext.** iVendNext calls nothing outside. The service **reads** iVendNext with the user's key: the rules, the price lists, the item prices, and the event feed. It **writes** item prices on the rules' target lists.

## Run it

```bash
python3 -m unittest discover -s samples/s26_derived_prices/tests -p 'test_*.py'
python3 samples/s26_derived_prices/tests/canaries.py
```

On a sandbox, with the integration user's key in the environment (never on the command line, never committed):

```bash
DPL_KEY=… DPL_SECRET=… python3 samples/s26_derived_prices/sync.py run --base https://your-sandbox.example --state state/dpl.sqlite --watch 5
DPL_KEY=… DPL_SECRET=… python3 samples/s26_derived_prices/sync.py reconcile --base https://your-sandbox.example --state state/dpl.sqlite
```

`backfill --rule ⟨name⟩` works one rule's list out again from the start; `status` prints the rules, the refused ones and the feed's backlog.

## The files

| File | What |
|---|---|
| `prices.py` | the rules, pure: the formula and its rounding in `Decimal` at the rule's decimal places, the rule checks (two currencies, a step too fine, two rules on one list, a loop), the stamp |
| `sync.py` | the service: iVendNext over the record API, the feed handler, the chain, the end date for a deleted source, the resumable backfill, the nightly reconcile |
| `manifest.json` | the `PP DPL Rule` record type, the role, the feed registration on Item Price |
| `tests/test_s26.py` | 29 laptop tests: the rounding table, the rule checks, one event twice, a person's price (and an ended one, which does not block), a rule switched off and on, a source's unit corrected, a chain and a loop, a deleted source, a crash in a backfill, a reconcile of each planted fault |
| `tests/test_manifest.py` | the manifest: valid, every field the rules read declared, the user's rights, nothing sent outside |
| `tests/canaries.py` | each guard removed in turn: its test must go RED (33 of 33) |

## Technical notes

- **Why a stamp.** The target row's *note* holds `PP-DPL ⟨rule⟩ ⟨source row⟩`. It is how a replayed event finds the row it made, how a deleted source finds its rows, and how a person's price is told apart: a row without the rule's stamp, or a stamped row whose *modified by* is not the service's own user (read once a pass with `ivendnext_mpos.api.v1.get_logged_user`).
- **Why a made row is found by its stamp alone.** If someone corrects the item or unit of a source price, the made row moves with it rather than a second row being made.
- **Why the service walks the chain.** The feed sends an application no event for its own writes, so a write to list B would never reach the rule from B to C. The service applies B's rules right after writing B.
- **Why an end date, not a delete.** A row ended yesterday stops selling and keeps its history; its *valid from* moves back when it is later, since iVendNext refuses an end before the start.
- **Money.** `Decimal` from the retailer's text to the price written back as text; a float never holds a price. The places are the rule's own (2 by default): iVendNext sizes every price from its system-wide currency precision, which the app's user may not read, so the retailer sets the rule to match it.

### What was proven where

- **The laptop tests** (`tests/`): everything above against a stand-in iVendNext; `canaries.py` turns each guard off in turn and its test goes RED.
- **A sandbox site** (2026-10-16, POS 2.0.0.648, manifest 0.1.0, the service on a laptop with the site's integration user): install with `tools/deploy`; a 1.5× rule backfilled 3 prices (29.985 → 29.99, 120.555 → 120.56, 75); a source changed to 66.67 and the target read 100.01 after 14.2 seconds; the retailer's own pricer (`ivendnext_mpos.api.v1.get_item_details`) returned 100.01 on the derived list; the same source saved again made 0 writes; a derived price a person edited and a person's own price were both held and reported; a deleted source sent `item_price.deleted` and its row was ended in 15.3 seconds, after which the pricer found no price; a full replay wrote 0; the reconcile read 0 differences with the 2 held prices listed; the uninstall exported and removed the rule, and the site's records, roles and permissions were as found. A second run the same day, after the review's changes (manifest 0.1.1, the decimal places field set to 2): the backfill wrote 2, a change followed in 12.6 seconds, a person's price that had ended did not block its item, a source price moved to another item moved its made row (no second row), the reconcile read 0 with nothing held, a replay wrote 0, and the site was as found again. Not run on a sandbox: a chain of lists, a loop, a crash in a backfill, a zero-decimal currency, a rule switched off and on, a unit corrected (the site has one unit), a source made a price for one customer: laptop only.
