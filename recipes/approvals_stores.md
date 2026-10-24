# Approvals across stores — a store manager's limit, head office above it — the recipe

![Requests in two stores: a store manager approves within their limit, head office above it, and the price row follows](../samples/s14_approvals_stores/screenshots/s14_flow.gif)

This recipe is [Approvals by workflow](approvals.md) (S11) grown for a chain. A price change names its **store**; **the store manager of that store** approves it up to a limit, and **head office** approves anything above; each store sees only its own requests; a small outside service applies the change **once**. **Reference implementation:** `samples/s14_approvals_stores/` (a manifest, an outside service, tests).

It keeps every safeguard S11 has. Read S11's recipe first: this page says only what is new.

**When to use it.** When the person who may approve depends on the store and on the size of the change, and the retailer has more than one store.

## Steps

1. **Four roles.** The install makes each role the manifest names that iVendNext does not have and that starts with your prefix, empty (on a site whose POS app is at `e149dce4` or later; an older install refuses the manifest for a role the site lacks). The sample names *PP APS Requester*, *PP APS Store Manager*, *PP APS Head Office* and *PP APS Applier*; the retailer gives each to the right people. In a real roll-out use the chain's own roles, which the install leaves as they are. ⚠ **No one holds a raising role and an approving role, and no one holds both approving roles.** The retailer's own self-approval check covers the *Approve* action only; the rest rests on this rule and on the service.

2. **Install the manifest** (`samples/s14_approvals_stores/manifest.json`; `recipes/manifest.md`). It holds two record types and one workflow:
   - the **price change request**: item, price list, **store** (fixed once raised), new price, reason, change tracking on;
   - the **approval rule** table: one row per person — *Store* with a store and a limit (a percentage of the price now), or *Head Office*;
   - a workflow of five states: *Requested → Store Approved → Head Office Approved → Applied*, and *Rejected*. The store manager approves or rejects; head office approves (from *Requested* or *Store Approved*) or rejects (from any); the service applies from either approved state.
   Every row writes all nine rights out. The store manager, head office and service can read and write requests; only the administrator's role writes the **rule table**, so no one can raise their own limit.

3. **Fence each person to their store — in the retailer's iVendNext.** For every requester and store manager, one *User Permission* on *POS Profile* (their store). iVendNext then shows them, and lets them approve, their own store's requests only; a requester cannot raise a request for another store. Head office and the service have no store fence: they see all stores.

   What each person sees: the store manager ![store manager's list](../samples/s14_approvals_stores/screenshots/01_list_store_manager.png) and head office ![head office's list](../samples/s14_approvals_stores/screenshots/02_list_head_office.png).

4. **Write the rules.** One row per approver: *Store*, their store, their limit (for example 10); or *Head Office*. A person with no row has no authority in the service's eyes, whatever role they hold.

5. **The service's key** is S11's (step 4 there): read and write on *Item Price*, fenced by a *User Permission* on the price lists it serves (*Applicable For* *Item Price* only), plus read and write on the request type (its workflow action saves the request) and read on the rule table. It cannot write a rule or raise a request.

6. **Run the outside service** (`approvals_stores.py apply`) as often as you like. For each request in *Store Approved* or *Head Office Approved*, oldest first, it checks, and only then writes the price and takes the *Apply* action — once, and a rerun after a kill finishes it without writing the price again. It refuses and says why:
   - S11's refusals: item, price list or price changed after it was raised (and now the **store**); ten or more recorded changes; no recorded approval; no or two price rows;
   - **an approval given by the person who raised the request — at any step, not only the last**;
   - **a store approval by someone without a *Store* rule for this request's store**, or whose rule is not whole (a Store rule needs a store and a limit above 0 — iVendNext stores a blank limit as 0 — and a rule row must be named by its person, so a row whose *Person* was edited is not believed);
   - **a store approval whose price row changed after the approval** (an earlier request applied, another role's edit): the limit was judged against a price that is gone, so the manager rejects it and it is raised again. This stops two requests approved side by side adding up past the limit — two +10% requests would otherwise make +21%; requests approved one after another each still move the price by up to the limit (below). A head-office approval names the price it wants and is applied whatever the row holds;
   - **a change above the store manager's limit** that head office has not approved: it waits, and the report says so;
   - **a head-office approval by someone without a *Head Office* rule**.
   - **a request rejected while the service was applying it**: the action fails, and the service puts the price back and says so — within one run. If a run was killed after writing the price and the request is rejected before the next run, no run looks at it again: check that price row by hand.

   A refusal is written only in the service's report: keep the report. The request's own history shows who approved at each step and the service's *Apply*.

   What it looks like: the manager's action ![the manager approves](../samples/s14_approvals_stores/screenshots/03_store_manager_approves.png), a change within the limit applied ![applied](../samples/s14_approvals_stores/screenshots/04_applied_within_limit.png), a change above the limit waiting ![waiting for head office](../samples/s14_approvals_stores/screenshots/05_over_limit_waits_for_head_office.png), then head office's yes and the service's apply ![applied after head office](../samples/s14_approvals_stores/screenshots/06_applied_after_head_office.png), and the price row ![the price row](../samples/s14_approvals_stores/screenshots/07_the_price_row.png).

7. **Schedule the export** (`approvals_stores.py export --day <date> --out <folder>`), as S11 step 6: the day's requests with the store and who approved at each step, who applied and who rejected, and a column *changed_after_raise* that says **yes** where the item, price list, price or store was edited after the request was raised (iVendNext lets a requester edit an *Applied* request; the history keeps the truth, and the file now says so). A cell that starts with `=`, `+`, `-` or `@` is written with a leading `'`, so a spreadsheet shows it as text.

## Know these limits

- **The rules are read when the service runs.** An approver whose rule was removed after approving is no longer believed (measured: the request is left alone, and applied once the rule is back); one whose limit was raised after approving is believed at the new limit.
- **The limit is per request, not cumulative.** Requests approved and applied one after another each move the price by up to the limit. A chain that wants a cap per day adds it.
- **The limit is read against the price at the moment the service runs**, and a store approval is valid only while the price row is as it was when approved (step 6). One request per price row at a time: a second one approved beside it is rejected and raised again.
- **Where several stores share one price list, one store manager's approval changes every store's price.** The rule table fences who approves, not whose price moves.
- **The approval binds this service only,** as in S11: take write on *Item Price* from every other role.
- **The service does not tie a price list to a store.** A store manager's approval moves the price on whatever list the request names — including another store's own list, if the requester named it. A retailer with one price list per store should add that check.
- **Putting a price back is best effort.** If iVendNext refuses the put-back itself, the report says only "the shop said …" while the rejected price stays live; a Desk edit to the price row in the milliseconds between the service's write and its put-back is overwritten.
- **An edit in the milliseconds between the service's read and its action** leaves the request *Applied* showing the edit, while the price written is the approved one; the export marks it *changed_after_raise*.
- **The service's key lists the retailer's users, with email, phone and mobile number.** Measured: 36 rows, fields `email`, `mobile_no`, `name`, `phone` — the retailer's default for any desk user, not a right this sample grants. If that matters to the chain, give the service a user the retailer's directory does not list, or accept it.
- **A negative price is refused** by the field (non-negative), and a price row at or below 0 is never inside a percentage.
- A person who holds both approving roles but only a *Store* rule can take the head-office action in the retailer's iVendNext (their roles allow it); the service does not believe it (measured). Keep roles and rules in step; where they differ, the rule table wins and the service errs on refusing.

## What is refused, and why

- **A store manager opening or approving another store's request; a requester raising one for another store:** refused by iVendNext.
- **A store manager taking the head-office action:** refused by iVendNext; head office's rule is the service's second lock.
- **A request raised and approved by one person:** iVendNext refuses the *Approve* action; a state written straight in is accepted by iVendNext and refused by the service — at the store step and at the head-office step.
- **A store manager writing a rule:** refused (the rule table is the administrator's).

## Technical notes

### What was proven, and where

- **Laptop, 35 tests** (`samples/s14_approvals_stores/tests/test_s14.py`): within the limit (the limit itself included) applied once, a second run changes nothing; above it nothing is written until head office approves; head office may approve straight from *Requested*; a store approver of another store, a person with no rule or an incomplete rule, a rule removed after approving, and a head-office state given by a store manager are not believed; a request raised and approved by one person is refused at the store step, at the head-office step, and when the raiser's approval was an earlier step; a price or store changed after it was raised is refused whoever changed it; nine recorded changes are applied and ten are not; a crash between the price and the action is finished without rewriting the price; the export holds exactly the day's requests, with the store and each step, in the same bytes twice; a reject landing while the service applies puts the price back; the export names who rejected. Twenty-four deliberate breakages of the service (each guard, old and new) were each caught by a test; two survivors found earlier led to tests.
- **On our test bench, 35 checks**: the install (five states, all drafts, ten transitions, no self-approval, change tracking on, the store fixed once raised, every right on both record types); a request on a rand price list holds that list's currency, which *New price* names; each person's list (store A's manager sees store A's request and not store B's, and the other way; head office and the service see both — the control); the other store's request refused to open and to approve; a request for another store refused to the requester; a change within the limit applied in each store, once; **two requests approved side by side in one store: the first applied, the second refused because the price changed after its approval (two approvals side by side cannot add up past the limit)**; a negative price refused by iVendNext; one above it left unapplied until head office approved, then applied; a store manager's forged head-office state refused by iVendNext, and the same forged by a person with both roles and one rule refused by the service; the approver's rule removed → refused, restored → applied; raised-and-approved by one person at both steps; the price changed before approving and after, by a requester and by the administrator; the store fixed once raised (a fenced manager and head office, who has no fence, are each refused — the second by the set-only-once rule); nine changes applied and ten refused; a kill between the price and the action finished by the rerun with no new price version; the service's narrow rights, and its price-list fence (a write on a list it is not fenced to is refused); the export, with the column that says an applied request was edited afterwards; everything the run made removed (the schema equals the one before; no POS day open).
- ⚠ **Not proven on the bench (laptop only):** a change of the item or the price list after the request was raised; the raiser's approval at an earlier step followed by head office's; a store approver of another store (the retailer's fence refuses them first).
- ⚠ **Not proven:** two services at once (one per retailer; no lock); many requests at once; approvals across companies; an approver who is also the applier; a requester raising a request in Desk with the sample's rows (the bench raised them through the API); a price list per store; the export's `TZ=` line (S11's, proven there).

- **Screenshots** (our test bench, 2026-10-10; frame: Desk, 1440 wide): the store manager *Andile Zwane* and head office *Elise Marais* signed in to Desk and pressed the workflow actions; the requests were raised through the record API by the requesters, and the service was run between shots. The service's own words for a change above the limit: *"above the store manager's limit (10.0%): the change is 33.3%; it waits for head office"*. The Desk forms are cut above the activity lines, which name the test users by address. The approval-rule table was not photographed.

### Measured

- iVendNext refuses a **state written straight in** when the writer's roles allow no such move (a store manager cannot write *Head Office Approved*), and **accepts** it when the writer's roles do (a person holding the raising and approving roles). This is why the service reads the rule table instead of the state.
- The service's key lists the retailer's **users with their email, phone and mobile number** (the retailer's default for any desk user): 36 rows, fields `email`, `mobile_no`, `name`, `phone`.
- Contact rows are created a moment after a new user: a before/after comparison of iVendNext must wait for them.
