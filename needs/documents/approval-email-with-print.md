---
id: approval-email-with-print
title: The approval e-mail carries the document's print
area: documents
topic: approvals
asks: An e-mail at each approval step with the purchase order's PDF attached, and the uploaded CSV
status: ready-with-limits
door: configure
blocked-by: -
recipe: recipes/configure_no_code.md
sample: none
request: -
verified: run on a sandbox 2026-10-16 · POS 2.0.0.650 · a notification with Attach Print saved, then deleted; not run: a mail sent
---
## What you build
A notification, in a manifest or set up in Desk by the retailer's administrator, on the approval step, with *Attach print* ticked and the print format chosen. In Print Settings, *Allow Print for Draft* must be on: with it off the notification raises an error on a draft or pending document, and as the notification runs inside the document's own save, that can stop the approval step.

## Limits
- An uploaded CSV goes as a **link** in the message: the installed framework has no attach-from-field, and a manifest cannot carry it (it could mail any private file). The link opens with the reader's own rights.
- *Allow Print for Draft* is a site-wide setting, and a notification that fails (no print, no recipient mail) can hold the document's save: send the first one to a test document.
- A manifest can carry the same notification, on any record type that is not one of the till's own: the approval recipe shows it.
- Not run: a mail sent with the print attached.

## Tell the customer
Each approval step mails the approver the document as a PDF; an uploaded CSV is a link in the same mail.
