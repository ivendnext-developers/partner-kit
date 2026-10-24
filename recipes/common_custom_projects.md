# Common custom projects, and the recipe that builds each — the recipe

Most custom projects a retailer asks for have been asked for before: a limit at the till, an approval, extra fields on a purchase order, a check against the retailer's own ERP, a screen on the shop floor. Each of them is now a card in the [needs catalogue](../needs/README.md): the need in the customer's words, the verdict, the way in, the recipe and sample to start from, and the limits to tell the customer. This page is how to use it. It is for a builder, or the salesperson beside them, turning a customer's wish list into a blueprint.

**Reference implementation:** none of its own. Each card names the recipe and sample that build it.

**When to use it.** At the blueprint step, before chapter 15's examples. One need, one card: if the need has a card, start from its recipe; if it has none, place it on the ladder yourself (chapter 3) or ask for an extension point (chapter 9).

## Steps

1. **Write the customer's needs as one list,** in the customer's own words: *"no more than 50 of one item on a line"*, not *"a quantity validator"*.
2. **Find each need's card.** On the partner site, the catalogue's A to Z list is in the customer's words, and the same cards are grouped by area, by door and by verdict. At a terminal:

   ```bash
   python3 tools/needs/needs.py search no more than 50 of one item     # the best cards first
   python3 tools/needs/needs.py show line-quantity-cap                 # one card
   ```

3. **Read each card's limits aloud to the customer.** Where the old system stopped the cashier at the keystroke, a check here often stops the sale at Pay. Most retailers accept that once they hear it, and some do not. The card's *Tell the customer* line is written for the proposal.
4. **Group the needs into as few apps as you can.** One service can answer the check before payment, a capture and a Desk button together (the [till guard rules recipe](till_guard.md) shows how), with one settings record the retailer edits.
5. **Mark what is *Not yet* or *Not possible*.** If no single door fits a *Not yet* need, compose doors before you ask for one: an outside app with a document check, a Desk button that asks for inputs, a partner page opened from a button, a capture at the scan, save rules and configuration combine to meet most needs. Write the composition and its limit (a separate screen, a tap, seconds of delay) in the blueprint row; that is the answer to give the customer. Ask for the card's extension point only when no composition meets the customer's outcome, and say which compositions you tried and why each falls short. A *Not possible* need stays closed: no script in the retailer's site, no change to iVendNext's code (chapter 3, the four rules).
6. **Fill the blueprint.** `python3 tools/needs/needs.py blueprint <id> <id> …` prints section (b) of the [project blueprint](../kit/blueprint.md), one row per card.

## The popular needs

The cards customers ask for most, listed from the catalogue when the partner site is built:

{{needs: popular}}

## What iVendNext needs from you

| You give | iVendNext checks |
|---|---|
| A blueprint that names, for each need, its card, its door and its limits | That every limit is one it accepts, before you build |
| One app per group of needs, not one per need | One card, one consent, one integration user |

## Technical notes

- **Sources.** The cards carry the doors, answers and limits that chapters 3, 4, 7, 9, 15 and 16 state, and the contract pages under `contracts/pages/`. Where a card and a chapter differ, the chapter is right; report the difference (chapter 17).
- **Fields on the retailer's own record types.** The manifest checker accepts a field on any of the retailer's record types, child tables included, when its name starts with your prefix. It refuses `reqd` and the keys the server enforces on every save (`default`, `unique`, `non_negative`, `length`, `set_only_once`, `precision`): see chapter 7.
- **The catalogue grows.** One need, one card. When a door a *Not yet* card waits for ships, its card moves to *Ready* or *Ready, with limits* and names its recipe. The format and how to add a card: [`needs/README.md`](../needs/README.md).
