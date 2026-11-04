# Approvals by workflow

A customer wants a person's yes before a document goes out. iVendNext's own workflow does it, and an app can install one on the customer's own record type. [S11](../samples/s11_approvals/README.md) is the worked example: a Purchase Order over 50,000 waits for a Purchase Manager, and approving it submits it.

**First, does the customer need an app at all?** If all they want is that an order over an amount needs a particular person or role, no: it is one record in iVendNext Desk. Open **Authorization Rule**, set **Transaction** to *Purchase Order*, **Based On** to *Grand Total*, **Authorized Value** to the amount, and **Approving Role** or **Approving User** to who may submit above it. Anyone else who tries to submit an order over that value is refused. An app earns its place when the customer wants named steps, a *Reject*, mail, or the same thing installed on many sites.

## The workflow

In `manifest.json`, under `workflows`:

```json
{
  "name": "ACME PO APPROVAL Purchase Order Approval",
  "document_type": "Purchase Order",
  "send_email_alert": 1,
  "states": [
    {"state": "Draft", "doc_status": 0, "allow_edit": "Purchase User"},
    {"state": "Approved", "doc_status": 1, "allow_edit": "Purchase Manager"},
    {"state": "Rejected", "doc_status": 0, "allow_edit": "Purchase User"},
    {"state": "Cancelled", "doc_status": 2, "allow_edit": "Purchase Manager"}
  ],
  "transitions": [
    {"state": "Draft", "action": "Approve", "next_state": "Approved", "allowed": "Purchase Manager", "allow_self_approval": 0, "condition": "doc.base_grand_total > 50000"},
    {"state": "Draft", "action": "Reject", "next_state": "Rejected", "allowed": "Purchase Manager", "condition": "doc.base_grand_total > 50000"},
    {"state": "Draft", "action": "Submit", "next_state": "Approved", "allowed": "Purchase User", "allow_self_approval": 1, "condition": "doc.base_grand_total <= 50000"},
    {"state": "Rejected", "action": "Review", "next_state": "Draft", "allowed": "Purchase User", "allow_self_approval": 1},
    {"state": "Approved", "action": "Cancel", "next_state": "Cancelled", "allowed": "Purchase Manager", "allow_self_approval": 1}
  ]
}
```

- **`doc_status`:** 0 keeps the document a draft, 1 submits it, 2 cancels it. Moving into a state with 1 submits the document, so the person who presses needs the right to submit it.
- **`allowed`:** the role that may press the action. **`allow_edit`:** the role that may edit the document in that state.
- **`allow_self_approval`:** 0 stops the person who raised the document taking this step, so nobody approves their own order; 1 lets them, and a step the buyer takes needs it. A step that says nothing is `0` on today's POS and takes Desk's own setting, `1`, from its next update, so name `0` on every step that must stay two-person.
- **`condition`:** when the action is offered, written with the document's fields (`doc.base_grand_total`, the total in the company's currency, or `doc.company`). Keep every state reachable: above, *Submit* takes what *Approve* does not.
- **`send_email_alert`:** 1 mails whoever may act next.

A role the site does not have is made at install, empty, for the customer to give to staff.

## More you can add in the same manifest

- **A required field,** for example a budget code the order must carry: under `custom_fields`, `{"dt": "Purchase Order", "fieldname": "acme_po_approval_budget_code", "fieldtype": "Data", "label": "Budget code", "reqd": 1, "insert_after": "supplier"}`. A field you add to the customer's record type starts with your app's prefix.
- **A mail when the order is submitted, with its print:** under `notifications`, `{"name": "ACME PO APPROVAL submitted", "document_type": "Purchase Order", "event": "Submit", "channel": "Email", "subject": "Purchase Order {{ doc.name }} is submitted", "message": "{{ doc.supplier }}: {{ doc.grand_total }}", "recipients": [{"receiver_by_document_field": "owner"}], "attach_print": 1}`.
- **Its own numbering:** under `naming_rules`, `{"document_type": "Material Request", "prefix": "MR-BLR-", "prefix_digits": 5}`.
- **More steps,** such as head office above a higher amount: another state and another transition, each with its own condition.
- **A reason asked on rejecting:** [A reason asked before a document is rejected](desk_action.md#a-reason-asked-before-a-document-is-rejected).
- **Each store's manager approves their own store's:** [Approvals across stores](approvals_stores.md).

## What it may not do

A workflow may run on any record type except the till's own (POS Invoice, the day's opening and closing, Customer, and what the till books), because a sale must never wait for an approval nobody at the counter gives. A state may write only your app's own field. The full list: [What an app may not do](../contracts/pages/what_an_app_may_not_do.md).

## Try it

```bash
ivn new acme_po_approval --from s11
cd apps/acme_po_approval
ivn check
ivn try
```

Then, on your sandbox: as the buyer, raise a Purchase Order over the amount; as the approver, open it and press **Approve**. It reads *Approved* and it is submitted. To remove it, uninstall it from **Retail Extension Package**: the workflow goes, and documents keep the state they were in.

## What to tell the customer

Orders over the amount wait for a Purchase Manager, and the buyer submits the rest. Whoever may act next gets a mail.
