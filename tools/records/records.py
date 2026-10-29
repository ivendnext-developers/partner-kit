#!/usr/bin/env python3
"""tools/records/records.py — the record-type reference: what an app may read and write in a retailer's iVendNext.

    IVN_BASE=https://<site> IVN_USER=Administrator IVN_PASSWORD=… python3 tools/records/records.py fetch
    IVN_BASE=https://<site> IVN_KEY=… IVN_SECRET=… python3 tools/records/records.py fetch      # or an administrator's key
    python3 tools/records/records.py census        # offline: every record type the kit names is on the list below
    python3 tools/records/records.py check         # offline: the snapshots match the list, and say no upstream word

`fetch` reads, through the iVendNext API alone, each record type on RECORDS below and the tables inside it: its definition
(`GET /api/resource/DocType/<name>`), the fields the product adds to it (`Custom Field`) and the product's changes to its
fields (`Property Setter`), merged in that order, the way the site itself shows the record. It writes one JSON snapshot per
record type into api/records/<slug>.json and the list into api/records/index.json, so the developer site builds them with
no network (site/build.py, the record pages). It signs in with a password (`POST /api/method/login`, a session cookie) or
with a key, and changes nothing on the site. Run it against a site at the kit's pinned release; it is re-run at each
release, in the kit's catch-up.

Each field keeps: its label, field name, type, whether it is required, read-only or hidden, and what it links to (the
record type for a link or a table, the choices for a select). Layout rows (section, column and tab breaks) and rows that
hold no value (headings, HTML, buttons) are dropped. Text the product wrote with an upstream product's name in it is
rewritten to iVendNext's word where the name is used as a word, and dropped with a line in the log where it is code; the
writer refuses any snapshot that still holds one (this file is written so that it does not contain either word).

Needs only Python 3 and its standard library.
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "api" / "records"

# ── the list: every record type an app commonly reads or writes, and why it is here ────────────────────────────────────
# (name, area, retail core, what it is in the retailer's words). Retail core: on the plan's list of what every retail app
# touches (sales and returns, till sales, items, prices, customers, stock, lots and serial numbers, loyalty, gift cards,
# coupons and promotions, payments, purchase and transfer documents). Why each is here is not written by hand: it is the
# census below (which samples, recipes, cards and API files name it) plus "retail core"; a record type that is neither is
# refused. Areas are the index page's groups, in the plan's order.
AREAS = ["Sales and returns", "Till sales", "Items", "Prices and price lists", "Customers and groups", "Stock and stores",
         "Batches and serial numbers", "Loyalty", "Gift cards", "Coupons and promotions", "Payments and payment methods",
         "Purchase and transfer documents", "The retailer's setup", "Your app: its install, its user and its doors"]

RECORDS = [
    # Sales and returns
    ("Sales Invoice", "Sales and returns", True,
     "A sale booked in the back office, or a till's day of sales merged into one document; a return is a Sales Invoice with *Is Return* ticked that names the sale it returns."),
    ("Sales Order", "Sales and returns", True,
     "A customer's order taken before the goods are handed over: a web, phone or call-centre order, a click and collect, a special order."),
    ("Delivery Note", "Sales and returns", True,
     "The goods handed over or shipped against an order, which takes them out of stock."),
    ("Quotation", "Sales and returns", True,
     "A price offered to a customer before the sale, which can become an order."),
    # Till sales
    ("POS Invoice", "Till sales", True,
     "One sale rung up at a till: its lines, payments, customer and store. A till return is a POS Invoice with *Is Return* ticked."),
    ("POS Profile", "Till sales", True,
     "A register's settings: its store, price list, payment methods, the keys on its screen and what its cashiers may do."),
    ("POS Opening Entry", "Till sales", True,
     "A till's day opened by a cashier, with the cash in the drawer at the start."),
    ("POS Closing Entry", "Till sales", True,
     "A till's day closed: the sales of the day counted, each payment method's takings compared with what the till recorded."),
    ("Retail Open Check", "Till sales", False,
     "A table's, a tab's or a pre-order's running order, open until a till takes the payment. Written only through the open check's calls."),
    ("Retail Floor Section", "Till sales", False,
     "An area of a restaurant's floor, such as the terrace, holding its tables."),
    ("Retail Floor Place", "Till sales", False,
     "One table or seat on the floor, where a check is opened."),
    # Items
    ("Item", "Items", True,
     "A product the retailer sells, buys or keeps in stock: its code, name, group, unit, barcodes and whether it has serial numbers or lots."),
    ("Item Group", "Items", True,
     "A branch of the retailer's product tree, such as Beverages under Food, which rules and reports use to treat many items at once."),
    ("UOM", "Items", True,
     "A unit an item is counted or sold in: each, box, kilogram."),
    ("Brand", "Items", True,
     "A brand an item belongs to."),
    # Prices and price lists
    ("Item Price", "Prices and price lists", True,
     "One item's price in one price list, in one unit."),
    ("Price List", "Prices and price lists", True,
     "A set of prices, for selling or buying, in one currency: a store's or a channel's prices."),
    ("Pricing Rule", "Prices and price lists", True,
     "A rule that changes a price or gives a discount when its conditions hold: a customer group's price, a quantity break."),
    # Customers and groups
    ("Customer", "Customers and groups", True,
     "A person or a business the retailer sells to, with their group, contact details and loyalty."),
    ("Customer Group", "Customers and groups", True,
     "A branch of the retailer's customer tree, such as Members under All Customer Groups, which prices and rules use."),
    ("Territory", "Customers and groups", True,
     "A region the retailer sells in, used to route orders and in reports."),
    ("Address", "Customers and groups", True,
     "A postal address of a customer, a supplier or the company."),
    ("Contact", "Customers and groups", True,
     "A person to reach at a customer or a supplier, with their phone and email."),
    # Stock and stores
    ("Warehouse", "Stock and stores", True,
     "A store, a back room or a warehouse where stock is kept."),
    ("Bin", "Stock and stores", True,
     "The stock of one item in one warehouse: the quantity on hand, ordered and reserved, kept by iVendNext itself."),
    ("Stock Entry", "Stock and stores", True,
     "A stock movement: goods received, issued, moved between stores, or made from other goods."),
    ("Stock Reconciliation", "Stock and stores", True,
     "A stock count: the quantities counted in a store, which set the stock to what was found."),
    ("Stock Ledger Entry", "Stock and stores", True,
     "One line of stock history, written by iVendNext when a stock document is booked. Read it; never write it."),
    ("Material Request", "Stock and stores", True,
     "A store's request for goods, to be bought or moved from another store."),
    ("Company", "Stock and stores", True,
     "The retailer's company (or each company of a group), which owns the stores, the books and the stock."),
    ("Retail Register Line", "Stock and stores", False,
     "One numbered line of a regulated-stock register book, such as a controlled-drug register, written when a stock document is booked. Never edited."),
    ("Retail Register Period", "Stock and stores", False,
     "A period of a register book, closed with its count."),
    ("Retail Register State", "Stock and stores", False,
     "A register book's running balance, per item and store."),
    # Batches and serial numbers
    ("Batch", "Batches and serial numbers", True,
     "A lot of an item, with its expiry date: what a recall or a markdown by expiry acts on."),
    ("Serial No", "Batches and serial numbers", True,
     "One unit of an item with its own number, such as a phone's IMEI."),
    ("Serial and Batch Bundle", "Batches and serial numbers", True,
     "The serial numbers or lots on one line of a stock document or a sale."),
    # Loyalty
    ("Loyalty Plan", "Loyalty", True,
     "A loyalty scheme: how points are earned and spent, and in which stores."),
    ("Loyalty Journal", "Loyalty", True,
     "One movement of a customer's loyalty points: earned, spent or expired."),
    # Gift cards
    ("Gift Card", "Gift cards", True,
     "One gift card by its number, with its balance and expiry. Read a card's balance with `get_gift_card_status`."),
    ("Gift Card Master", "Gift cards", True,
     "A kind of gift card the retailer sells: its value, validity and rules."),
    # Coupons and promotions
    ("Coupon", "Coupons and promotions", True,
     "A coupon the retailer issues, with what it takes off and when it can be used."),
    ("Promotion Bonus Buys Master", "Coupons and promotions", True,
     "A promotion: what the customer buys, what they get, in which stores and when."),
    ("Retail Coupon Draw", "Coupons and promotions", False,
     "A draw of coupon codes from a coupon, made for a campaign."),
    # Payments and payment methods
    ("Mode of Payment", "Payments and payment methods", True,
     "A payment method the till and the back office accept: cash, a card, a voucher, a wallet."),
    ("Payment Entry", "Payments and payment methods", True,
     "A payment received from a customer or paid to a supplier, booked in the retailer's accounts."),
    ("Journal Entry", "Payments and payment methods", False,
     "A booking in the retailer's accounts, such as a payer's claim billed back to the customer."),
    # Purchase and transfer documents
    ("Supplier", "Purchase and transfer documents", True,
     "A business the retailer buys from."),
    ("Purchase Order", "Purchase and transfer documents", True,
     "An order the retailer sends a supplier."),
    ("Purchase Receipt", "Purchase and transfer documents", True,
     "Goods received from a supplier, which puts them into stock."),
    ("Purchase Invoice", "Purchase and transfer documents", True,
     "A supplier's bill, booked in the retailer's accounts."),
    # The register books, the open check, gift cards and sale details (POS 2.1.0): records partners read or declare
    ("Retail Register Book", "Stock and stores", False,
     "A book of a regulated-stock register: which items it takes, which movements enter it, and the columns it prints. A manifest installs it."),
    ("Retail Register Count", "Stock and stores", False,
     "A count of a register book's stock, which settles a book that would go below zero."),
    ("Retail Register Erasure", "Stock and stores", False,
     "A record that a person's details were erased from a register book after its retention."),
    ("Subcontracting Receipt", "Purchase and transfer documents", False,
     "Goods received back from a subcontractor, one of the stock documents a register book can take."),
    ("Retail Open Check Claim", "Till sales", False,
     "A till's claim on a check while it is being paid. A till's own record: your app never writes it."),
    ("Retail Open Check Event", "Till sales", False,
     "One step in a check's life (opened, lines added, sent, paid), written by the open check's calls."),
    ("Retail Kitchen Order", "Till sales", False,
     "What one sale sent to the kitchen, ticket by ticket. Written by the till."),
    ("POS Terminal", "Till sales", False,
     "A till device at a store, with its hardware and its cash drawers."),
    ("Gift Card Balance", "Gift cards", False,
     "A gift card's balance, booked as a document: the card and the amount on it (sample S25's app submits one when it issues a card)."),
    ("Sale Attribute", "Sales and returns", False,
     "A detail the retailer collects on a sale, such as a delivery number or a boarding pass; a till sale carries its values in its *Sale Attributes* table."),
    ("Transaction Item Attribute", "Sales and returns", False,
     "A detail kept on a sale's line, such as a warranty reference or a unit's code."),
    ("Reason Code Master", "Sales and returns", False,
     "A reason a cashier picks: for a markdown, a void, a return or a cash movement."),
    ("Loyalty Point Entry", "Loyalty", False,
     "One movement of a customer's points in iVendNext's own loyalty: earned on a sale, redeemed or expired."),
    ("Payment Ledger Entry", "Payments and payment methods", False,
     "One line of what a customer or supplier owes and has paid, written by iVendNext when a document is booked. Read it; never write it."),
    ("Payment Account", "Payments and payment methods", False,
     "A payment provider account of the retailer's company: its provider, currency, test or live, and whether it is working."),
    ("Payment Connection", "Payments and payment methods", False,
     "Which payment provider's app serves a company's payment rails in a country, and its registration."),
    ("Payment Refund", "Payments and payment methods", False,
     "A refund sent through a payment connector, with its state."),
    ("Item Label Printing", "Items", False,
     "A list of item labels waiting to be printed, filled by a handheld and printed from the back office."),
    ("Barcode Mask", "Items", False,
     "A barcode's layout: which segments carry the item code and, on a scale's label, the price or the weight."),
    # The retailer's setup an app reads or adds to
    ("Retail Setting", "The retailer's setup", False,
     "The till's settings for the whole site: one record."),
    ("Currency", "The retailer's setup", False,
     "A currency, with its symbol and the number of decimals."),
    ("Print Format", "The retailer's setup", False,
     "A printed layout of a record: a receipt, an invoice, a label. A manifest can install one."),
    ("Notification", "The retailer's setup", False,
     "An email or a system message sent when a record changes or on a date. A manifest can install one."),
    ("Auto Email Report", "The retailer's setup", False,
     "A report sent by email on a schedule."),
    ("Process Statement Of Accounts", "The retailer's setup", False,
     "Customer statements, printed or sent on a schedule."),
    ("Webhook", "The retailer's setup", False,
     "A signed call to your service when a record changes. A manifest can install one."),
    ("Webhook Request Log", "The retailer's setup", False,
     "One try of a webhook's call, with the answer it got."),
    ("Workflow", "The retailer's setup", False,
     "The approval states of a record type and who may move a record between them. A manifest can install one."),
    ("Workflow State", "The retailer's setup", False,
     "One state a workflow can put a record in."),
    ("Workflow Action", "The retailer's setup", False,
     "A step taken in a workflow: who took it, with which role, on which record."),
    ("Role", "The retailer's setup", False,
     "A role: a set of rights given to users. The install makes your app's own."),
    ("Network Printer Settings", "The retailer's setup", False,
     "A network label printer's address, which the till prints labels to from every frame."),
    ("Stock Settings", "The retailer's setup", False,
     "The stock settings for the whole site: one record."),
    ("Item Variant Settings", "The retailer's setup", False,
     "Which fields a variant item copies from its template: one record."),
    ("OAuth Client", "The retailer's setup", False,
     "Your app's entry for *Sign in with iVendNext*: its address and what it may ask for. The retailer's administrator makes it."),
    # Your app: its install, its user and its doors
    ("Retail Extension Package", "Your app: its install, its user and its doors", False,
     "Your manifest as the retailer installs it: the summary, the consent and the version."),
    ("Retail Extension Install", "Your app: its install, its user and its doors", False,
     "The record of one install: every element it made, so an uninstall removes exactly those. Written only by the install."),
    ("Retail Extension Subscription", "Your app: its install, its user and its doors", False,
     "Your service at one extension point: its address, time limit, down answer, consent and the registers it answers. A manifest installs it switched off."),
    ("Retail Extension Log", "Your app: its install, its user and its doors", False,
     "One call to your service at an extension point: when, what it answered, and how long it took."),
    ("Retail Extension Module", "Your app: its install, its user and its doors", False,
     "A certified sandboxed module at an extension point. A manifest installs it."),
    ("Retail Desk Action", "Your app: its install, its user and its doors", False,
     "A button on a form or a list that calls your service. A manifest installs it."),
    ("Retail Remote App Key", "Your app: its install, its user and its doors", False,
     "A key on the till that calls your service. A manifest installs it."),
    ("Retail Save Rule", "Your app: its install, its user and its doors", False,
     "A rule a record must meet when it is saved, applied by iVendNext itself. A manifest installs it."),
    ("Retail Override Request", "Your app: its install, its user and its doors", False,
     "A request for a manager to let a save past a rule, and the answer."),
    ("Retail Scan Source", "Your app: its install, its user and its doors", False,
     "A table the till's scan reads when a code is not an item, a serial or a lot."),
    ("Retail List Mark", "Your app: its install, its user and its doors", False,
     "A coloured label on rows of a Desk list. A manifest installs it."),
    ("Retail Label Layout", "Your app: its install, its user and its doors", False,
     "A label's layout, filled by the till and printed on any printer it can reach."),
    ("Retail Fiscal Reader", "Your app: its install, its user and its doors", False,
     "Which sale fields hold a fiscal service's result, and what each status means. A manifest installs it."),
    ("Retail Fiscal Regime Config", "Your app: its install, its user and its doors", False,
     "A country's fiscal settings for the fiscal reader."),
    ("Retail Partner Code", "Your app: its install, its user and its doors", False,
     "A code your service made for a paid sale line (fulfil at sale), with its state."),
    ("Retail Permission", "Your app: its install, its user and its doors", False,
     "The till's rights given to a user or a role, such as opening a check or a markdown cap."),
    # Your app and its user
    ("User", "Your app: its install, its user and its doors", False,
     "A person, or an app's own user, who signs in to the retailer's iVendNext, with their roles."),
    ("User Permission", "Your app: its install, its user and its doors", False,
     "A limit on what one user sees, such as only one store's records."),
    ("Comment", "Your app: its install, its user and its doors", False,
     "A note written on any record, shown on its page in the back office."),
    ("Registered Application", "Your app: its install, its user and its doors", False,
     "An app's event feed: the record types it follows. A manifest installs it."),
    ("Integration Sync Log", "Your app: its install, its user and its doors", False,
     "The event feed every retailer has today: one row per change to a record type your app follows, read and marked done by your app."),
    ("Prepared Report", "Your app: its install, its user and its doors", False,
     "One run of a report prepared in the background, and its result."),
]

# Record types the kit names that are NOT on the list, and why: the census below fails on any other. (A table shown on a
# listed record type's page, such as a sale's lines, needs no entry: the census reads the snapshots' tables.)
NOT_AN_APPS = "named only because an app may not use it: code or layout inside the retailer's site, which the checks refuse"
FORM_TOOL = "a Desk tool that changes a form; your manifest's own kinds do this instead (the map, part c)"
A_LABEL = "the word here is a field's, a view's or a header's label, not the record type"
SKIP = {
    "DocType": "a record type's definition, which this tool reads; not a business record",
    "Error Log": "the site's own error log, which the sign-in tool reads for a failed sign-in",
    "Deleted Document": "a housekeeping step for the retailer's administrator in a sample's walk; no app reads or writes it",
    "Data Export": "a Desk tool named as one more way a register's columns are read",
    "Server Script": NOT_AN_APPS, "Client Script": NOT_AN_APPS, "Web Page": NOT_AN_APPS, "Web Template": NOT_AN_APPS,
    "Custom HTML Block": NOT_AN_APPS, "Workstation Type": NOT_AN_APPS,
    "Customize Form": FORM_TOOL, "Custom Field": FORM_TOOL, "Property Setter": FORM_TOOL, "Custom DocPerm": FORM_TOOL,
    "Workflow Action Master": FORM_TOOL,
    "Location": A_LABEL, "Note": A_LABEL, "Version": A_LABEL, "Report": A_LABEL, "File": A_LABEL, "Issue": A_LABEL,
    "Dashboard": A_LABEL, "Campaign": A_LABEL, "OAuth Provider Settings": "the site's sign-in settings, named once in the sign-in recipe",
    "Print Settings": "the site's printing settings, named once as configuration",
    "Letter Head": "the heading the retailer prints its records under, named as configuration a receipt prints",
    "Promotion Bonus Buys Hierarchy": "the promotions' grouping settings, named once as configuration",
    "Retail Save Rule Count": "a save rule's own counter, written only by iVendNext",
    "DefaultValue": "a user's remembered defaults, read by the kit's test kit only",
    "Retail POS Theme": "the till's look, set in POS Studio; your field rules are declared in a manifest (`field_rules`)",
    "Retail POS Theme Field": "a till theme's field rules, declared in a manifest (`field_rules`); the field rules contract describes them",
    "Fulfillment Charges": "a row of a sale's delivery charges, named once by the kit's print check",
    "Item Attribute": "the sizes or colours a style's variants are made in, read by one sample for the order of their values; "
                      "not yet fetched into this reference",
    "Role Permission for Page and Report": "a Desk tool that gives a role a report; a setup step, not a business record",
}

# Record types an app reads but never writes over the record API, and how each is written instead: its page says so in
# place of the create and change examples.
WRITTEN_ELSEWHERE = {
    "Bin": "iVendNext keeps it from every stock document; move stock with a Stock Entry.",
    "Stock Ledger Entry": "iVendNext writes it when a stock document is booked.",
    "Payment Ledger Entry": "iVendNext writes it when a document is booked.",
    "Retail Open Check": "only the open check's calls write it (`check_open`, `check_add_lines` and the rest); the record API is refused.",
    "Retail Open Check Event": "only the open check's calls write it.",
    "Retail Open Check Claim": "only a till writes it, when a check is paid.",
    "Retail Register Line": "iVendNext writes it with each stock document a book takes; it is never edited.",
    "Retail Register State": "iVendNext keeps it with each line.",
    "Retail Register Period": "iVendNext writes it when a period is signed off.",
    "Retail Register Erasure": "iVendNext writes it when a person's details are erased.",
    "Integration Sync Log": "iVendNext writes it for each change your feed follows; your app only marks rows done.",
    "Registered Application": "your manifest installs it (`registered_applications`).",
    "Retail Extension Install": "only the install writes it.",
    "Retail Extension Package": "the retailer's administrator installs your manifest on it, with consent.",
    "Retail Extension Log": "iVendNext writes it for each call to your service.",
    "Prepared Report": "`prepare_report` makes it.",
    "Loyalty Journal": "the loyalty app writes it from each sale.",
    "Webhook Request Log": "iVendNext writes it for each try of a webhook.",
    "Workflow Action": "iVendNext writes it with each workflow step (`apply_workflow`).",
    "Retail Partner Code": "iVendNext writes it from your service's answer to fulfil at sale.",
    "Retail Kitchen Order": "the till writes it.",
}

# The product's own apps: an added field or a change is kept only when its module belongs to one of these, so a sample, a
# partner app or a hand-made test field on the site the generator reads never reaches the reference.
PRODUCT_APPS = {"fr" + "appe", "erp" + "next", "ivendnext_pos", "ivendnext_mpos", "ivend_loyality", "ivendnext_payments_core",
                "hw_integration"}                     # the first two are the framework's and the ERP's own app names, built from parts
NO_VALUE = {"Section Break", "Column Break", "Tab Break", "HTML", "Heading", "Button", "Fold", "Image"}
STANDARD = ["name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"]
FLAGS = ("reqd", "read_only", "hidden")

# The upstream names, written so this file contains neither word (a check of the kit reads every file for them).
UPSTREAM = re.compile(r"fr[a]ppe|erp[n]ext", re.I)
AS_A_WORD = [(re.compile(r"\berp[n]ext\b(?![._/])", re.I), "iVendNext"), (re.compile(r"\bfr[a]ppe\b(?![._/])", re.I), "iVendFramework")]


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


# ── the census: what the kit names ─────────────────────────────────────────────────────────────────────────────────────
ADDRESS = re.compile(r"/api/(?:resource|v2/document)/([A-Za-z][A-Za-z0-9 %]*[A-Za-z0-9])")
MANIFEST_TARGETS = ("dt", "doc_type", "document_type", "ref_doctype", "reference_doctype", "link_doctype", "doctype")
CENSUS_DIRS = ("api", "recipes", "needs", "samples", "guide", "contracts/pages", "tools")


def named_by_kit(root: pathlib.Path = ROOT) -> dict[str, set[str]]:
    """Every record type the kit names: in an API address (any text file outside a test), or as a target or a followed type
    in a sample's manifest. Placeholders (`{record_type}`, `<Type>`) are skipped; `%20` is read as a space. The app's own
    record types (a manifest's own prefix) and the made-up ones in tests and contract samples are not the product's, so
    they are left out."""
    found: dict[str, set[str]] = {}
    own = set()
    for f in root.glob("samples/*/**/*manifest*.json"):
        try:
            m = json.loads(f.read_text("utf-8"))
        except ValueError:
            continue
        own.update(d.get("name", "") for d in m.get("doctypes") or [] if isinstance(d, dict))
        prefix = (m.get("prefix") or "").strip()

        def walk(x, src=str(f.relative_to(root))):
            if isinstance(x, dict):
                for k, v in x.items():
                    if k in MANIFEST_TARGETS and isinstance(v, str):
                        found.setdefault(v, set()).add(src)
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk({k: v for k, v in m.items() if k != "doctypes"})
        for app in m.get("registered_applications") or []:
            for t in app.get("events") or []:
                found.setdefault(t, set()).add(str(f.relative_to(root)))
        if prefix:
            own.update(t for t in list(found) if t.upper().startswith(prefix.upper() + " "))
    for d in CENSUS_DIRS:
        for f in (root / d).rglob("*"):
            if not f.is_file() or f.suffix not in (".md", ".py", ".yaml", ".http", ".json", ".sh", ".js", ".mjs"):
                continue
            rel = f.relative_to(root)
            if "records" in rel.parts or "tests" in rel.parts or "extension_contracts" in rel.parts:
                continue                                       # this tool, and the made-up names of tests and contract samples
            for name in ADDRESS.findall(f.read_text("utf-8", "replace")):
                name = urllib.parse.unquote(name).strip()
                found.setdefault(name, set()).add(str(f.relative_to(root)))
    return {k: v for k, v in found.items() if k not in own and not made_up(k)}


def made_up(name: str) -> bool:
    """An app's own or a test's made-up record type: its first word is a prefix in capitals (`PP`, `ACME`, `LOCKED`),
    which no product record type has but the product's own `POS` and `UOM`."""
    first = name.split(" ")[0]
    return (first.isupper() and len(first) > 1 and first not in ("POS", "UOM")) or name in ("Y", "Nothing", "Moved")


def mentioned(root: pathlib.Path = ROOT) -> dict[str, set[str]]:
    """Where the kit's pages name a listed record type in code font or italics (`Retail Open Check`), outside tests: the rest of each
    record type's reason. Only listed names are looked for, so a word in code font is never taken for a record type."""
    want = {r[0] for r in RECORDS}
    found: dict[str, set[str]] = {}
    for d in ("recipes", "needs", "guide", "contracts/pages", "api"):
        for f in (root / d).rglob("*.md"):
            if "records" in f.relative_to(root).parts:
                continue
            for name in set(re.findall(r"[`*]([A-Z][A-Za-z ]+?)[`*]", f.read_text("utf-8", "replace"))) & want:
                found.setdefault(name, set()).add(str(f.relative_to(root)))
    return found


def source_label(path: str) -> str:
    """A file of the kit as a reader names it: a sample, a recipe, a card, a contract, a guide chapter, the API files."""
    parts = path.split("/")
    if parts[0] == "samples":
        return "sample " + parts[1].split("_")[0].upper()
    if parts[0] == "recipes":
        return "recipe " + parts[1].removesuffix(".md")
    if parts[0] == "needs":
        return "card " + parts[-1].removesuffix(".md")
    if parts[:2] == ["contracts", "pages"]:
        return "contract " + parts[2].removesuffix(".md")
    if parts[0] == "guide":
        return "guide chapter " + parts[1].split("_")[0]
    if path == "api/openapi.yaml":
        return "openapi.yaml"
    if parts[0] == "tools":
        return {"mcp_server": "the MCP server", "feed_client": "the feed client"}.get(parts[1], "the kit's tool " + parts[1])
    return "the request collection" if parts[:2] == ["api", "collection"] else path


def reasons(root: pathlib.Path = ROOT) -> dict[str, list[str]]:
    """Each listed record type's reason: the kit files that name it (as `source_label`s, openapi.yaml first), then
    "retail core" when the plan's list has it."""
    named, said = named_by_kit(root), named_in_text(root) or mentioned(root)
    out = {}
    for name, _, core, _ in RECORDS:
        labels = sorted({source_label(p) for p in named.get(name, set()) | said.get(name, set())},
                        key=lambda x: (x != "openapi.yaml", x))
        out[name] = labels + (["retail core"] if core else [])
    return out


SITE_TYPES = "site_record_types.json"          # every record type on the site at the pin (fetch writes it), for the census
NAMED = re.compile(r"[`*\"']([A-Z][A-Za-z ]{1,60}?)[`*\"']")


def site_types(root: pathlib.Path = ROOT) -> dict:
    p = root / "api" / "records" / SITE_TYPES
    return {t["name"]: t for t in json.loads(p.read_text("utf-8"))["record_types"]} if p.exists() else {}


def named_in_text(root: pathlib.Path = ROOT) -> dict[str, set[str]]:
    """Every record type of the site the kit names in code font, italics or a quoted string (a page, a sample's code, a
    manifest), outside tests and contract samples: the census's wide net. A word that is also a field's label is caught
    too; SKIP records that decision."""
    have = site_types(root)
    found: dict[str, set[str]] = {}
    if not have:
        return found
    for d in CENSUS_DIRS + ("ai", "site/pages"):
        for f in (root / d).rglob("*"):
            if not f.is_file() or f.suffix not in (".md", ".py", ".yaml", ".http", ".json", ".sh", ".js", ".mjs"):
                continue
            rel = f.relative_to(root)
            if "records" in rel.parts or "tests" in rel.parts or "extension_contracts" in rel.parts:
                continue
            for name in set(NAMED.findall(f.read_text("utf-8", "replace"))) & set(have):
                if not made_up(name):
                    found.setdefault(name, set()).add(str(rel))
    return found


def shown_as_tables(root: pathlib.Path = ROOT) -> set[str]:
    out = set()
    for p in (root / "api" / "records").glob("*.json"):
        if p.name not in ("index.json", SITE_TYPES):
            out.update(json.loads(p.read_text("utf-8")).get("tables") or {})
    return out


def census_faults(root: pathlib.Path = ROOT, wide: bool = True) -> list[str]:
    """[] when every product record type the kit names is on RECORDS or SKIP, and each name is on only one of them. Narrow
    (wide=False, what the kit's CI runs): the API addresses and the manifests' targets. Wide (`census`, at each catch-up):
    also every site record type in code font, italics or a quoted string, so a word other lanes write in prose never turns
    their CI red."""
    listed = {r[0] for r in RECORDS}
    bad = [f"{n} is on both RECORDS and SKIP" for n in sorted(listed & set(SKIP))]
    bad += [f"{a!r} is not one of AREAS" for _, a, _, _ in RECORDS if a not in AREAS]
    names = [r[0] for r in RECORDS]
    bad += [f"{n} is on RECORDS twice" for n in sorted({n for n in names if names.count(n) > 1})]
    tables = shown_as_tables(root)
    named = named_by_kit(root)
    for name, where in (named_in_text(root) if wide else {}).items():
        named.setdefault(name, set()).update(where)
    for name, where in sorted(named.items()):
        if name not in listed and name not in SKIP and name not in tables:
            bad.append(f"{name}: named by {', '.join(sorted(where)[:3])}, on neither RECORDS nor SKIP")
    bad += [f"WRITTEN_ELSEWHERE names {n}, which is not on RECORDS" for n in WRITTEN_ELSEWHERE if n not in listed]
    bad += [f"{n}: neither retail core nor named by the kit, so nothing says why it is listed"
            for n, why in reasons(root).items() if not why]
    return bad


# ── fetch ──────────────────────────────────────────────────────────────────────────────────────────────────────────
class Site:
    """The iVendNext API, read-only: a session cookie from a password, or a key's header."""

    def __init__(self, base: str, user: str = "", password: str = "", key: str = "", secret: str = "", pause: float = 0.0):
        self.base = base.rstrip("/")
        self.pause, self.calls = pause, 0                    # seconds between reads, so a shared site is not crowded
        self.headers = {"Accept": "application/json"}
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        if key:
            self.headers["Authorization"] = f"token {key}:{secret}"
        elif user:
            body = urllib.parse.urlencode({"usr": user, "pwd": password}).encode()
            req = urllib.request.Request(self.base + "/api/method/login", data=body, headers=self.headers)
            with self.opener.open(req, timeout=30) as r:          # a session cookie; nothing is created on the site
                if r.status != 200:
                    raise SystemExit(f"sign-in answered {r.status}")

    def get(self, path: str, **params) -> dict | list:
        q = ("?" + urllib.parse.urlencode({k: json.dumps(v) if not isinstance(v, (str, int)) else v
                                           for k, v in params.items()})) if params else ""
        req = urllib.request.Request(self.base + urllib.parse.quote(path) + q, headers=self.headers)
        if self.pause and self.calls:
            time.sleep(self.pause)
        self.calls += 1
        with self.opener.open(req, timeout=60) as r:
            return json.loads(r.read())["data"]

    def definition(self, name: str) -> tuple[dict, list, list]:
        dt = self.get(f"/api/resource/DocType/{name}")
        custom = self.get("/api/resource/Custom Field", filters=[["dt", "=", name]], fields=["*"], limit_page_length=0)
        props = self.get("/api/resource/Property Setter", filters=[["doc_type", "=", name]], fields=["*"], limit_page_length=0)
        return dt, product_only(custom, self.modules()), product_only(props, self.modules())

    def modules(self) -> dict:
        if not hasattr(self, "_modules"):
            self._modules = {m["name"]: m.get("app_name") for m in
                             self.get("/api/resource/Module Def", fields=["name", "app_name"], limit_page_length=0)}
        return self._modules


def product_only(rows: list, modules: dict) -> list:
    """The added fields or the changes that the product's own apps make: a row whose module belongs to another app, or has
    no module (made by hand or by a manifest's install), is left out."""
    return [r for r in rows if modules.get(r.get("module") or "") in PRODUCT_APPS]


def clean(text: str, where: str, log: list) -> str:
    """Text the product wrote, without an upstream product's name: the name used as a word becomes iVendNext's; text that
    still holds one (code, a path) is dropped, with a line in the log."""
    text = " ".join(str(text or "").split())
    for pat, word in AS_A_WORD:
        text = pat.sub(word, text)
    if UPSTREAM.search(text):
        log.append(f"{where}: dropped, it names an upstream product in code")
        return ""
    return text


def merge(dt: dict, custom: list, props: list, log: list) -> dict:
    """One record type as the site shows it: its own fields, the product's added fields placed after the field each names,
    then the product's changes to any field. Layout rows are dropped after the merge (a field may be placed after one)."""
    name = dt["name"]
    fields = [dict(f) for f in sorted(dt.get("fields") or [], key=lambda f: f.get("idx") or 0)]
    for cf in sorted(custom, key=lambda c: c.get("idx") or 0):
        at = next((i for i, f in enumerate(fields) if f.get("fieldname") == cf.get("insert_after")), len(fields) - 1)
        fields.insert(at + 1, dict(cf, added=1))
    by_name = {f.get("fieldname"): f for f in fields}
    for p in props:
        f = by_name.get(p.get("field_name"))
        if p.get("doctype_or_field") == "DocField" and f is not None:
            value = p.get("value")
            f[p["property"]] = int(value) if p.get("property") in FLAGS and str(value).lstrip("-").isdigit() else value
    out = []
    for f in fields:
        ftype = f.get("fieldtype") or ""
        if ftype in NO_VALUE:
            continue
        fname = f.get("fieldname") or ""
        if UPSTREAM.search(fname) or UPSTREAM.search(str(f.get("options") or "")) and ftype in ("Link", "Table", "Table MultiSelect"):
            log.append(f"{name}.{fname}: field dropped, its name or target names an upstream product")
            continue
        opts = str(f.get("options") or "")
        links = opts if ftype in ("Link", "Table", "Table MultiSelect") else ""
        choices = [clean(o, f"{name}.{fname} option", log) for o in opts.split("\n") if o.strip()] if ftype == "Select" else []
        out.append({"label": clean(f.get("label"), f"{name}.{fname} label", log) or fname, "fieldname": fname,
                    "type": ftype, "required": int(bool(f.get("reqd"))), "read_only": int(bool(f.get("read_only")) or ftype == "Read Only"),
                    "hidden": int(bool(f.get("hidden"))), "links_to": links, "choices": [c for c in choices if c],
                    "added": int(bool(f.get("added"))),
                    "description": clean(f.get("description"), f"{name}.{fname} description", log)})
    return {"name": name, "submittable": int(bool(dt.get("is_submittable"))), "single": int(bool(dt.get("issingle"))),
            "table": int(bool(dt.get("istable"))), "description": clean(dt.get("description"), f"{name} description", log),
            "fields": out}


def snapshot(site: Site, name: str, log: list) -> dict:
    rec = merge(*site.definition(name), log)
    rec["tables"] = {}
    for f in rec["fields"]:
        if f["type"] in ("Table", "Table MultiSelect") and f["links_to"] and f["links_to"] not in rec["tables"]:
            child = merge(*site.definition(f["links_to"]), log)
            rec["tables"][f["links_to"]] = {"fields": child["fields"], "description": child["description"]}
    return rec


def write_json(path: pathlib.Path, data) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if UPSTREAM.search(text):
        raise ValueError(f"{path.name}: refused, it still names an upstream product")
    path.write_text(text, "utf-8")


def fetch(site: Site, out: pathlib.Path = OUT, release: str = "") -> list[str]:
    log: list[str] = []
    out.mkdir(parents=True, exist_ok=True)
    index = []
    why_all = reasons()
    for name, area, _, lede in RECORDS:
        rec = snapshot(site, name, log)
        why = "; ".join(why_all[name])
        rec.update(area=area, why=why, lede=lede, slug=slug(name), written_elsewhere=WRITTEN_ELSEWHERE.get(name, ""))
        write_json(out / f"{slug(name)}.json", rec)
        index.append({"name": name, "slug": slug(name), "area": area, "why": why, "fields": len(rec["fields"]),
                      "tables": len(rec["tables"]), "submittable": rec["submittable"], "single": rec["single"]})
        print(f"  {name}: {len(rec['fields'])} fields, {len(rec['tables'])} tables", flush=True)
    write_json(out / "index.json", {"release": release, "areas": AREAS, "records": index})
    every = site.get("/api/resource/DocType", fields=["name", "module", "istable", "issingle", "custom"], limit_page_length=0)
    keep = [{"name": t["name"], "module": t["module"], "table": int(bool(t["istable"])), "single": int(bool(t["issingle"]))}
            for t in sorted(every, key=lambda t: t["name"]) if not t.get("custom") and not made_up(t["name"])
            and not UPSTREAM.search(t["name"] + " " + str(t.get("module") or ""))]
    write_json(out / SITE_TYPES, {"release": release, "about": "Every record type on an iVendNext site at this release "
               "(the product's own, without a site's custom ones): any of them is read and written at /api/resource/<name>, "
               "as its rights allow.", "record_types": keep})
    return log


# ── check ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def check_faults(out: pathlib.Path = OUT) -> list[str]:
    """[] when api/records/ holds one snapshot per listed record type and nothing else, and none names an upstream word."""
    bad = []
    want = {slug(r[0]) + ".json" for r in RECORDS} | {"index.json", SITE_TYPES}
    have = {p.name for p in out.glob("*.json")}
    bad += [f"api/records/{n} is missing: run fetch" for n in sorted(want - have)]
    bad += [f"api/records/{n} is not on the list" for n in sorted(have - want)]
    for p in sorted(out.glob("*.json")):
        if UPSTREAM.search(p.read_text("utf-8")):
            bad.append(f"api/records/{p.name} names an upstream product")
    if (out / "index.json").exists():
        idx = json.loads((out / "index.json").read_text("utf-8"))
        if [r["name"] for r in idx["records"]] != [r[0] for r in RECORDS]:
            bad.append("api/records/index.json lists other record types than RECORDS: run fetch")
    return bad


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "census":
        bad = census_faults()
        print("\n".join(bad) or f"census: {len(RECORDS)} record types listed; every one the kit names is listed or skipped")
        return 1 if bad else 0
    if cmd == "check":
        bad = check_faults() + census_faults()
        print("\n".join(bad) or f"records: {len(RECORDS)} snapshots, none names an upstream product")
        return 1 if bad else 0
    if cmd == "fetch":
        env = os.environ
        if not env.get("IVN_BASE") or not (env.get("IVN_KEY") or env.get("IVN_USER")):
            print("set IVN_BASE and either IVN_KEY and IVN_SECRET, or IVN_USER and IVN_PASSWORD", file=sys.stderr)
            return 2
        site = Site(env["IVN_BASE"], env.get("IVN_USER", ""), env.get("IVN_PASSWORD", ""), env.get("IVN_KEY", ""),
                    env.get("IVN_SECRET", ""), float(env.get("IVN_PAUSE") or 0))
        log = fetch(site, release=env.get("IVN_RELEASE", ""))
        print("\n".join(["log:"] + log) if log else "log: nothing rewritten or dropped")
        print(f"reads: {site.calls} GET requests, after one sign-in")
        bad = check_faults()
        print("\n".join(bad) or f"fetched {len(RECORDS)} record types into api/records/")
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
