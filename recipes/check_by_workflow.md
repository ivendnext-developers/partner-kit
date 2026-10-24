# A back-office check that blocks a document (check by workflow) — the recipe

**Since the POS app's train T11 (2026-10-16) there is a direct door for this:** the document check asks your service when the document is submitted and applies its answer ([recipe](document_check.md), sample S34). Use this workflow recipe on a site from before that release, or when the check must run after the save, from the event feed.

Some checks must **stop** a document until they pass: a goods receipt that must match what was ordered, or carry a code for every unit, before it is booked. Inside the retailer's iVendNext that would be code run at submit, which partners do not ship. This recipe gets the same result with **configuration and your own service**: the document's workflow books it only at a *Verified* step that only your service can take. It is for an iVendNext Partner, or the CitiXsys Consulting Team.

**Reference implementation:** `samples/s22_customer_loyalty/` — `apply_config.py` (`receipt_workflow`) and `service/receipts.py`: a Purchase Receipt is verified only when no row receives more than its purchase order still waits for.

**When to use it.** The check reads data your service holds or reads over the API, and the people submitting can wait a few seconds. For a check on the till's sale before payment, use a check before payment ([recipe](rule_guard.md)); for a format or a limit on one record's own fields, a save rule (chapter 7).

## Steps

1. **The workflow** (configuration, over the API — a manifest may not put a workflow on the retailer's own record types):

   | State | Books the document | Who may move it on |
   |---|---|---|
   | Draft | no | the clerk: *Send for Verification* |
   | Pending Verification | no | **your service's role only**: *Verify* · a manager: *Override* |
   | Overridden | **yes** | — |
   | Verified | **yes** | — |

   ⚠ List **Overridden before Verified.** A submit through the API that steps around the workflow lands in the first state that books; listed first, it is recorded as *Overridden*, never as *Verified*.

   ⚠ **Self-approval:** allow it on *Send for Verification* (the clerk sends their own document on) and refuse it on *Verify*, *Override* and cancelling. With every step refusing it, the clerk who made a document cannot even send it.

2. **Take the submit right from every other role** on that record type (the retailer's Role Permissions Manager, or `apply_config.py`). A workflow alone does not stop a submit through the API; without this step anyone with the submit right books the document unchecked. Keep it for your service's role (the *Verify* step books the document) and the manager's (the *Override* step). Record every row you change, and its reason.

3. **Your service follows the record type on the event feed.** Each save of a document in *Pending Verification* writes an event, a moment after the save. Read the document, run your check, then (the key that reads the document also needs read on the records it names, such as a receipt's supplier):
   - **passes:** take the *Verify* action through the API (`ivendnext_mpos.api.v1.apply_workflow`); the document books;
   - **fails:** leave it where it is and add a comment saying why, in words the clerk can act on.

4. **Act once.** A document already past *Pending Verification* is left alone, so a replayed event changes nothing.

5. **Test it:** your check on the laptop (the sample's tests), then on a sandbox: *Verify* refused for the manager and taken by your service; a clerk's submit refused before *Verified*, in the form **and** through the API; *Override* refused for a role that does not hold it.

## What is refused, and why

- **A workflow in your manifest on the retailer's own record types,** and any state that books a document: the manifest checker refuses both, because a workflow there changes the retailer's own documents. It is configuration the retailer's administrator applies, with an undo.

## When your service is down, and when the till is offline

- **Down:** documents wait in *Pending Verification*. A manager can *Override*. Nothing is booked unchecked.
- **Offline:** back-office documents are not booked offline; the till is not involved.

## Technical notes

### Bounds

- The clerk waits a few seconds for *Verified* (the feed).
- The site's Administrator holds every role, so it can always submit.
- The manager who holds *Override* can also submit through the API; it lands as *Overridden*.
- Once your service's user has taken *Verify*, your remove step can switch that user and its role off but cannot delete them. iVendNext keeps a record of each step taken, naming who took it, and only the site's Administrator can see those records.

### What was proven where

- **Laptop:** the sample's tests (the check, verified once, the submit right left only to the manager and the service, *Overridden* listed first, the permission rows put back on remove), each with a canary.
- **Test bench** (2026-10-09, on a site in the sandbox's shape and on a second site with a unit-count check): *Verify* refused for the manager and the administrator, and taken by the service's user, which books the document; a clerk's submit refused through the form and through the record API (`docstatus: 1`, and `ivendnext_mpos.api.v1.submit`); *Override* refused for the clerk and taken by the manager, recorded as *Overridden*; a document the check refused stayed in *Pending Verification* with the service's comment.
