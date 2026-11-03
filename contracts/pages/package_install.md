<!-- Source: ivendnext/iVendNext_PWA docs/extending/package_install.md @ 99b5d44fb7a3, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Installing a manifest (self-service install)

**Contract:** [`package_manifest.v1.schema.json`](../extension_contracts/package_manifest.v1.schema.json)
· samples: [`samples/package_manifest/`](../extension_contracts/samples/package_manifest/)
· code: `business_logic/extension_package.py` (the screen's and the API's methods), `business_logic/manifest_check.py`
(the checker), `business_logic/manifest_install.py` (the installer) · the screen: **Retail Extension Package** in
iVendNext Desk.

> **Package or module?** A **partner app (package)** is a partner's whole app: its records, fields, print formats, buttons,
> services and label layouts. You paste the partner's file, read *What it will do*, consent and install. Later you can
> update it or remove it. *Connected apps* lists every one. A **partner module** is one small program from a partner
> that does one job at an extension point, such as adjusting a price or checking a sale before payment. You upload the
> partner's file and the certificate our review team signs, and can withdraw it. A package can carry a module our certify
> service signed, with the service that runs it (§11); you can also add both by hand in iVendNext Desk ([the check before
> payment](partner_check.md), [pricing](price.md)). **In short:** a package is the app; a module is one program that
> does one job.

## 1. What it is and when it runs

A partner's own data for a shop (its record types and fields, print formats, workspaces, reports, workflows, and the
declarations of its buttons and services) travels as one **manifest**: a description, not a program. The shop's own
administrator installs it, updates it and removes it from a screen in iVendNext Desk. A partner's sandbox does the same
over the API. Nobody from our team takes part, and nothing goes through our cloud.

Our code is the gate, and it cannot be skipped. An app may do what the shop's administrator can do in Desk; the
checker refuses only what is on [what_an_app_may_not_do.md](what_an_app_may_not_do.md), each with its reason. Every check
and every install runs it inside the site, then the site's own checks (a name another app holds, a record type the site
lacks). The job checks again when it runs.

## 2. Version

Version 1 of the package. The manifest itself names `manifest_version` 1 or 2 and must carry a `version` written as
`major.minor.patch` (for example `0.1.0`), compared as numbers.

## 3. The screen, step by step

1. **New Retail Extension Package**: paste the partner's `manifest.json` and press **Check**. The record is named
   `<app> <version>`; there is one record per version.
2. **Refused because** lists every refusal in the checker's own words. Nothing is made.
   Among them, the record's room: a row of a record type declares at most 65,535 bytes (the database's own
   ceiling), shared by every app and the shop's own fields, and a short text field (Data, Link, Select) takes 562.
   The check measures each record type the manifest adds fields to, and each record type the app brings, on this
   site, and refuses one whose fields would not fit, in one line: the room left (in bytes, and as Data, Link or Select fields), what the
   fields need, the three widest, and where else they fit (the app's own record type; a sale detail for a short value
   on the sale; `Small Text`, 10 bytes, for text nothing searches). An update counts only what it adds or widens. The
   job measures again before it makes anything. MariaDB only (the framework has no Postgres estimate);
   `manifest_install._width_refusals`, pinned to the framework's estimate by `tests/test_manifest_width.py`.
   Not measured: a display change (`property_setters`) setting an own field's `length` (the install writes it without
   altering the column, which keeps its declared width), and the database's second row limit (about 8,126 bytes of a
   row's values stored in the row itself, under its strict mode), which the framework does not estimate either. An
   install that meets that limit still stops on the database's error, and the field whose column failed is left behind:
   **Finish** does not remove it (it is not on the app's record), the administrator deletes it.
3. **What it will do** is a summary our code writes from the manifest itself, never from the partner's own description:
   every record type, field (by its fieldname, and by its label in quotes, since 2.0.0.660) and role; every outside address with
   what it sends, and every help address a help link opens (since 2.0.0.660: its own line under *Connects outside your site*, never
   a display change); everything that runs from the moment of install (webhooks, notifications and who receives them,
   active workflows, sale details every till offers under *Sale details* from its next start, as optional — the
   installer makes each one not required, and the checker refuses a required one, and a sale detail with a list says
   which (§3, *A sale detail that lists your records*) — and display changes to the shop's
   own fields); and every print
   format, listed as **a template that runs when printed**,
   on the server, able to read and change the shop's records and call outside addresses, as one the administrator
   writes by hand can (the one thing the checker cannot fully judge). **Check also writes the same lines in plain
   words** (`summary_parts`, since 2.0.0.645: one part per line, written by a plain writer per kind next to the summary's), and the
   screen draws those under five headings: *New in Desk* · *Who can use it* · *Changes to what you already have* ·
   *Print layouts* · *Connects outside your site* (that last one always shows, and never reads as nothing beside a print
   layout). Lists that say the same thing share one sentence (*Location, Aisle, Bin: new lists*); each heading's ids,
   fields and rights as written fold under *Show details*. Every fact a line pins (each role and right, each outside
   address, *switched off*, *every Desk user*, *never added to the menu*, when it starts) is in its plain sentence, never only in the
   details. The plain words are **not** what is consented to: the summary is, and it is fingerprinted. The record keeps
   the plain words as Check wrote them, in the language of whoever pressed Check, and never rewrites them once
   consented to; the exact wording is always the server's English. A record checked
   before 2.0.0.645 has no plain words and is drawn line by line, word for word, under the same headings (a line no heading
   knows stays whole under *Other*). *Show as text* shows the stored summary.
4. **Consent and install** opens *Install ⟨app⟩* (*Update ⟨app⟩*): the same drawing, the checker's warnings (stored at
   Check beside the plain words), who can install here, *Show the exact wording* (the summary, byte for byte), and the
   tick *I agree to everything above and to the exact wording*. **Install** stays disabled
   until it is ticked. The server stamps who and when, with the
   SHA-256 of the summary and of the exact manifest. A consent never carries over to other content, even when the
   summary reads the same. One exception, for the same manifest only: version 2.0.0.660 reworded three lines (a sale detail said
   every till *asks* for it; a help address read as a display change; a field was named by its code alone), and a
   consent given to those words before 2.0.0.660 still holds for the same manifest at install and at the job — so a version
   consented before 2.0.0.660 installs again at its version. No old line covered less of what the install grants (the label
   a field line now adds is a name, already bound by the manifest's SHA-256); a till key's line, which did, still needs
   a higher version (since 2.0.0.646). The old words are frozen in the code and hold only a consent already
   given to them: every new consent is to today's words (a record checked before 2.0.0.660 and never consented
   refuses the old fingerprint with *"check again"*; its **Check** shows today's words). A label is the
   partner's words: the plain sentence shows it, whole and in quotes, only because the exact line holds it. The install runs as a background job; the status moves Queued → Installing → Installed.
5. **Secrets** (a webhook's or a service's) are shown once, to the user who installed, when the job ends. Each can be
   read again on its own record, with *Copy secret* (§12). Hand them to the partner as you would an integration user's
   key. An app hosted by CitiXsys receives them from the site itself when it connects (§10).
6. **One consent switches everything on.** The install's consent is each part's: every service (a Desk button's
   service, a page, a check before payment, a capture), every Desk button, label layout, list mark, scan source and the
   event feed's record types arrive **switched on**, for every store, consented by the user who consented to the
   package and when. A **till key** arrives consented and on, placed on every store's till (in each theme's POS
   Studio > Apps), just before the till's last key; a store moves or hides it in the Designer. A record's **Enabled**
   box stays the administrator's off switch. **Before each part works** lists only what the shop still decides: a
   fiscal reader (its writer rule and the service's keys), a role rule (switched on it would stop everyone until
   someone holds its role), a payer service (its clearing mode is the shop's account), a pricing module's limit (0
   until the shop raises it), a check's POS Profiles and manager approval, a POS Profile with no till theme (no till
   key reaches it), a register book's warehouse map, and *Allow Print for Draft* when it is off.
   A **register book** (`register_books`, manifest version 2 — [register_books.md](register_books.md)) is installed
   on or off as it declares; an update never switches it, and an uninstall keeps a book with lines switched off.
   A **save rule** arrives **switched on** too. The exception is a role rule (*only named roles may submit or cancel*):
   the app's roles are created empty, so switched on it would stop everyone. It arrives off, and its line names the
   role to give first. An app's
   maker keeps any rule off with `"enabled": 0`, and the summary says so. A derived rule that would write a field
   another switched-on rule already writes is refused at the check, in the rule's own words.
   Webhooks, notifications, workflows and sale details arrive **switched on**, and a till theme's field rules have
   no switch at all (a require rule is enforced at once; the others reach each till at its next start): the package consent is theirs, which is
   why the summary names each one.

**The app's roles, and the administrator.** A role the manifest names that the site does not have (on a record
type's permission rows, a notification's recipients, a report, a chart, a workflow's states and steps, a Desk
button, a page, a save rule's bypass) is created at install, as named, with no one in it. A role named with the
app's prefix is the app's own and goes when no installed app uses it; any other name (*PO Approver*) is the shop's from
then on and stays at uninstall. A role the site already has is used as it is. The summary lists them: *Roles it uses: …
Those this site lacks are created empty.* A role the shop made itself is never removed. A manifest may not use another
installed app's fiscal writer role. A permission row's rights that the manifest leaves out are off. Every record type the app makes also gives **System Manager every right**, unless
the manifest already gives System Manager its own row at level 0 (then that row, as written), so the shop's
administrator can use the app at once and hand it to any role with Desk's own *Role Permissions Manager* and the
user's roles. iVendNext adds no permission screen of its own.

**A field only named roles read or change (`read_roles`, `write_roles`).** A field the manifest adds may say who
changes it and, optionally, who reads it: a licence number only the pharmacists see, a *barred* tick everyone sees
and only the claims clerks change.

```json
{"dt": "Customer", "fieldname": "pp_rxl_licence", "fieldtype": "Data", "label": "Licence number",
 "read_roles": ["PP RXL Pharmacist"], "write_roles": ["PP RXL Pharmacist"]}
```

- `write_roles` (required once a field is limited): the roles that change it; they read it too.
- `read_roles` (optional): the roles that read it. Left out, every role that reads the record type when the app
  installs reads it. A role given that record type later reads the field once the shop also gives it the field's
  level in *Role Permissions Manager*.
- The installer puts the field at a **permission level of its own** on that record type (the lowest of 1 to 9 that
  no field and no permission row there uses, one per set of roles), with one permission row per role. Two apps, or
  two sets of roles, never share a level. The summary says who reads and who changes each such field. The uninstall
  removes the rows with the field.
- On Desk, the form, the lists and the API leave the field out for anyone else, and a change from anyone else is
  undone when the record saves.
- On the till: a **Customer** field shows on the customer card and is searched or scanned only for a cashier
  whose roles read it, online. It never rides the offline customer book, for anyone: the book belongs to the
  device, and a teammate who takes the till offline reads the same book. A device holding a copy from before
  clears its book and fills it again. An **Item** field limited to roles is never shown on a till or a receipt,
  for anyone, even one everyone reads but only some change: the offline catalogue belongs to the device too.
- Refused: a limited field that is mandatory (`reqd`, `mandatory_depends_on`), a layout or table field, a fiscal
  reader's result field, and a print format or notification of the same manifest that names a field only some roles
  read (it would print or send it to whoever prints or receives it). A field everyone reads but only some change may
  be printed. The check reads every print format, notification, report, number card and chart the manifest ships,
  on any record type. A **register book** writes what it names whoever submits the document, so it may name such a
  field only for a person's column — a detail slot (`details`) or the counterparty (`columns_from`) — which only a
  role given that level of the line reads ([`register_books.md`](register_books.md) §8); it is refused for the
  authority (`authority.desk_fields`), the dispenser's licence, the reference number (`columns_from` →
  `reference_no`) and the item's class (`class_source`: take the items by `item_groups` instead), which every reader
  of the book's lines reads (`refused/29_a_register_book_naming_a_field_only_some_roles_read.json`).
- An update may add a limited field. It may not change the roles of a field already installed: ship a new field, or
  the shop changes the rows in *Role Permissions Manager*. Each install or update takes a new level for each set of
  roles it brings, even a set an earlier version already uses, and a record type has nine: group a kit's limited
  fields into few role sets.
- On a field with `read_roles`, System Manager gets no row unless the manifest names it: only the Administrator
  reads such a field without one (the opposite of a record type of the app's own, where System Manager always has
  a row). Without `read_roles`, System Manager reads it if it reads the record type. It changes it only when
  `write_roles` names it.
- A row the shop itself adds at an app's level stays after the uninstall, and that level stays taken. On a record
  type that had only its standard permission rows, the first limited field copies them into the shop's own rows
  first (as any custom row does), and the copies stay after the uninstall: the same rights.
- Two packages installed on one site at the same moment may both pick the same free level. Install one at a time.
- ⚠ Not closed by a level, on any record type: until your site runs the engine update that fixes it, the record's
  change history still answers a reader below the level about the value. The Administrator reads every field. A field a person must never be able to infer belongs on a record type of the
  app's own, whose permission rows decide who reads the whole record.

The intro line names the roles that may install here. The permission is the package record's own (System Manager by
default). A role given it in Role Permissions Manager gets System-Manager powers through the installer, which makes
roles, users and permission rows; grant it as you would grant System Manager.

### Help addresses

An app gives its screens a help page with a property setter. On its own record type: `{"doc_type": "<its record
type>", "property": "documentation", "value": "https://…/page#heading"}`. Every screen of that record type then
shows a `?` icon beside the printer that opens the page in Desk's help panel, beside the screen, at the `#heading`
(and the empty list's *Need Help?* link opens it there too). A docs.ivendnext.com page opens in the panel; an
address on another site opens in a new tab. On a field it adds to a shop's record type: the same with `field_name`
and `documentation_url` (the help icon beside the field's label, which opens in the panel the same way). In a setter value, a record type's description or a field's
label the check refuses markup carrying script (a script element, an inline handler, a `javascript:` address). The help address installs with the app, changes in place on an update and goes at uninstall.

A Desk page or a report has no help field: it declares its address from a Desk script with
`ivendnext_mpos.v1.help_link("query-report/<report name>", [{label: "<topic>", url: "https://…"}])` (a page: its
route name as the first argument). The link goes into the Help menu; the panel opens the list's first
docs.ivendnext.com address, and an address on another site shows in the Help menu only. A Desk script's address is not
checked at install. A script of your own can open a page in the panel with `ivendnext_mpos.v1.open_help(url)`. Both
names come with the POS app's Desk scripts and are never removed once published. Your app requires the POS app, so it
installs after it and its Desk scripts run after the POS app's; a site without the POS app has neither name, so check
first. Register only where the name exists: `if (window.ivendnext_mpos && ivendnext_mpos.v1) ivendnext_mpos.v1.help_link(…)`.
Open with a new tab as the fallback: `window.ivendnext_mpos && ivendnext_mpos.v1 ? ivendnext_mpos.v1.open_help(url) :
window.open(url, "_blank", "noopener")`.

### Desk pages (workspaces)

A workspace is your app's page, opened from the App library. It is never added to the menu. The install writes it out
of the Desk's menu (`custom_hide_from_menu`), limited to the roles your manifest names plus System Manager, and after
every page the site has. The shop's administrator opens it with the App library's **Open**; a user holding one of your
roles, or the site's Workspace Manager, finds it with the search bar or its route, `/app/<page name>`; nobody else sees
it. Showing it in the menu is the shop's own choice: a Workspace Manager clears *Hide from Menu* on the page's Workspace
record (the theme's menu editor does not list a page that belongs to no module, and a Workspace Manager does not see it
in their own menu: the app's role holders do). An update keeps that choice and the
page's place: it rewrites the page's content, shortcuts and icon, moves its roles to the ones your new version names
(also when only a record type's permissions changed), keeps a role the shop added and leaves out one the shop took off,
and skips a page the shop deleted (the update's list of changes still names it). A page the shop opened to everyone
(no roles) stays open, though an update's consent still names your roles. The consent says so: *Workspace ⟨name⟩, for ⟨roles⟩: opened from the App library or
the search bar, never added to the menu*. A manifest has no way to add a page to the menu. Pages an earlier version of
the installer put in the menu are taken out by a patch at the update (a page the shop made, roles the shop set on a page,
and a page the shop hid, stay); a page of an app with no installed package record keeps no roles, so the shop limits it.
A shortcut may open a report the same manifest adds: the install writes your pages after your reports, and an
update adding a page with its report does the same.
On the page, a user sees the shortcuts to the record types their roles read (a System Manager, who gets a row on each
record type unless the shop removes it, sees them all). The install and an update clear every user's cached rights
once they finish, so a user already signed in sees a record type the update added when the page next loads, without
signing in again (a page already open shows it after a reload).

### Reports

A manifest report is a Report Builder report over one record type (`ref_doctype`): Desk's report screen opens it with
its `columns`, in that order, its `filters` applied, and with a totals row when `add_total_row` is set. (A report installed before 2.0.0.654 opened with Desk's default columns instead. It gets its own columns when
its app is reinstalled, or updated with that report changed: an update leaves an unchanged report as it is.)
A report, a number card or a chart over a shop's record type may name a field the same manifest adds to it
(`custom_fields`), in one package: the install makes your fields first. So may a date notification's `date_changed` and
its `{{ doc.field }}` placeholders.

**Columns from one table of the record.** A column or a filter may name a field of the record's rows as
`table.field`: `items.qty` on Stock Reconciliation lists one line per item row, with the count's own columns (its
date, its number) repeated on each line. A count with no rows shows once, its row columns empty. A filter on the
table lists the record once per matching row, even when no column reads the table, and leaves out a record with no
rows.

- Name one table per report (two tables multiply each other's rows), and keep `order_by` a field of the record
  itself: it is the one part of a report the check reads, because it is written into the report's query.
- `table` is a table field of the record type and `field` a field of its rows. On a shop's record type the table may
  be one the same manifest adds (a table custom field pointing at one of your child record types): the install makes
  your fields before your reports.
- With a table's rows and a totals row, leave out a number column of the record itself: it repeats on every line, so
  the totals row would add it once per line. Desk also mixes two tables whose rows share a record type, and does not
  check a table's permission level for its rows.
- A document column and a row column with the same field name (`discount_amount` and `items.discount_amount`) show
  apart on Desk's screen, but a report e-mailed on a schedule names its values by field name alone, so there one
  overwrites the other: give the report one of them.
- Desk opens the report sorted by the record type's own default (or the user's last sort), not by `order_by`; the
  user picks the sort on the screen. `order_by` is what the server's reader uses.
- The totals row adds the lines on screen (Desk's page of lines), not every line in the database, and only number
  fields (Int, Float, Currency, Percent, Duration): a read-only column such as a count line's quantity difference
  stays blank in it.

**Who sees what.** The shop's rights are the framework's own; the notes above keep a package's report
honest, they fence nothing (any user may add the same row columns in Desk's own column picker, and a level the shop
raises later is not re-checked). A user who cannot read the record type is refused the
report. A row field the user may not see (one at a permission level they lack) is left out, and the rest shows. A
branch user's user permission fences the record by the record's own links, so the user sees every line of a record
they may open, which is exactly what that record's own form shows them.

### Notifications on the shop's records

A manifest notification may use any event and any recipient by role or by a field of the record, on any record
type, as the shop's administrator can in Desk: *mail the buyer when a Purchase Order is submitted, with its
print attached*. The consent names each recipient. Two limits:

- On **the till's own records** (the sale, the day's opening and close, the records the till's booking writes, and
  Customer, Contact and Address) it is only **Days Before** or **Days After** a date. Any other event runs inside the
  till's save, and an error in it would stop the sale. iVendFramework sends the two date events once a day from its
  scheduler, never in a save.
- E-mail or the in-app bell, to the shop's own people (by role, or by a field of the record): never to an address
  the manifest names, which the consent could not show.
- A `condition` compares the record's own fields with plain values (`doc.grand_total > 50000 and doc.status ==
  "Open"`), and the subject and message call nothing: all three are evaluated with a Server Script's globals,
  database writes included, inside the save that sends it. Use `{{ doc.⟨field⟩ }}`.
- A recipient field the app adds carries no default (the consent could not show that address), no file is attached
  by a field (`attach_files`, `from_attach_field`), and a field set after the alert (`set_property_after_alert`) is
  one of the app's own.

```json
{"name": "PP EXP Batch Expiry", "document_type": "Batch", "event": "Days Before", "days_in_advance": 30,
 "date_changed": "expiry_date", "channel": "Email",
 "subject": "Batch {{ doc.name }} expires on {{ doc.expiry_date }}",
 "message": "Batch {{ doc.name }} of {{ doc.item }} expires on {{ doc.expiry_date }}.",
 "recipients": [{"receiver_by_role": "Stock Manager"}]}
```

- A Date field the same manifest adds to a shop's record type (`custom_fields`) may carry the reminder, and a
  placeholder may name any field it adds: the install makes your fields before your notifications.

**What the shop accepts, as it does for the same notification set by hand in Desk:**

- **No cap.** One message per record whose date falls exactly on the day, however many there are.
- **Every holder of the role receives every record, whatever store they are fenced to**: the role's members are read
  without their user permissions. A placeholder shows its field to every one of them, even a field at a permission
  level the role cannot see in Desk.
- **A template error skips one message** (it is logged as *Failed to send Notification*) and the run goes on.
- **An error outside the template stops the day's run** for every date notification on the site that comes after
  it, the shop's own included: a record deleted while the run reads it, or a date field the shop removes later. Each
  record already sent stays sent (one commit per record). Name a Date field the record type has.
- Our own digest job (one message per day listing the records, each alert guarded) is the revisit, on a shop
  reporting a flood, a stopped run, or a branch that must receive only its own store's records.

### Multi-select fields, settings records and a notification's own print

**A multi-select field** (`Table MultiSelect`): a tag-like list on a record, picked from a list (Gender on Item,
Brands on Supplier). Like a table, it points at one of the manifest's own child record types; that child must have a
Link field **shown in the list** (`"in_list_view": 1`), because each choice is a row holding one link, to one of the
app's own record types or to a shop's (Brand), and Desk drops, when it saves a form, every child row none of whose
fields is shown in the list. The same holds for a plain table field (`Table`): give its child type a field shown in the list, one a person types
into, or the rows are lost at the save. It may sit on the app's own record types or, as a field the manifest adds, on a
shop's.

```json
{"dt": "Supplier", "fieldname": "pp_hkd_brands", "fieldtype": "Table MultiSelect", "label": "Brands",
 "options": "PP HKD Brand Pick"}
```

**A field that links to any record type** (`Dynamic Link`): its `options` name another field on the same record type that
says which record type it links to, a Link to `DocType` or a `Select` (iVendFramework's own rule, checked when the
field is saved). A field the manifest adds names one listed before it in the manifest, or one the record type has.

**A workflow on the shop's record type** installs as written: a state may submit or cancel, a transition may carry a
condition (it reads the record and two read-only helpers), and the mail goes as `send_email_alert` says. The first
workflow on a record type makes iVendFramework add its *Workflow State* field there; it stays at uninstall, as the
shop's, as it does when a workflow made in Desk is deleted.

**A list's settings** (`list_settings`): any record type may set how its Desk list looks, the shop's (Purchase Order)
as well as the app's own: `disable_count`, `disable_sidebar_stats`, `disable_comment_count`, `disable_auto_refresh`,
`total_fields`, and `fields`, the columns to show. Name `fields` only when the app means to choose the columns: an entry with no `fields`
(or an empty one) leaves the list's columns as Desk makes them. An entry that names
`fields` shows those, beside the title and the tags, and nothing else.

**A settings record** (`"issingle": 1`): one record, no list, the way every settings screen of the product works
(*HKD Settings*: a shelf-life threshold, a bypass role). Desk opens its form straight away; a service reads it at
`/api/resource/⟨type⟩/⟨type⟩`.

- Name it only where a record is read by its name: a property setter, a workspace shortcut that opens its form, a save
  rule's `value_from_type` and `value_from_name`. A list, a report or a date notification on it reads a table it does
  not have. An update may not change `issingle`: ship a settings record under a new name.

**A print format on the app's own record type** prints as one on a shop's record type does (since 2.0.0.660): the installer gives
every package print format this app's module (`iVendNext mPOS`), because the app's own prefix module is in no installed
app's module list and printing it refused *Module ⟨prefix⟩ not found*. A format installed before the fix is repaired at
migrate (`patches/v0/package_print_format_module.py`: only formats an install record lists whose module does not
resolve). ⚠ Bound: the formats now belong to this app's module, so uninstalling the iVendNext POS app itself (never
done on a live site) removes them with it, while the package's record types stay.

**A notification's own print.** A notification may attach a print of its record, on any record type: the record type's
default print, or a print format named in `print_format`:

```json
{"name": "PP HKD Complaint Mail", "document_type": "PP HKD Complaint", "event": "New", "channel": "Email",
 "subject": "Complaint {{ doc.title }}", "message": "A complaint was raised.",
 "recipients": [{"receiver_by_role": "System Manager"}],
 "attach_print": 1, "print_format": "PP HKD Complaint Slip"}
```

- **The attached print is rendered with no rights applied** and mailed to the shop's own people: show the record's own
  fields. `ivn_rows` and `ivn_value` return nothing in a mail (no viewer to read as), so do not rely on them here.
- **What the shop accepts:** every holder of the role receives it, in every store; the PDF shows everything the
  format shows; no size cap beyond one rendered print. On the bell the print is a link that opens with the viewer's
  own rights.
- **Keep Print Settings > Allow Print for Draft on** (it is on by default). The app's own record types are never
  submittable, so every record is a draft; with the setting off, iVendFramework drops the message and logs it
  (*Failed to send Notification*), and the record still saves, though every save shows an *Error in Notification*
  message. The install's to-do list says so.

### A sale detail that lists your records

A sale detail can offer a dropdown of one of your own record types, so a cashier picks a project from your list
instead of typing it. The install sets it up, with no step in Desk:

```json
{
  "doctypes": [
    {
      "name": "ACME PQT Project",
      "autoname": "format:ACME-PQT-{#####}",
      "title_field": "title",
      "show_title_field_in_link": 1,
      "fields": [{ "fieldname": "title", "fieldtype": "Data", "label": "Title" }]
    }
  ],
  "sale_attributes": [
    {
      "name": "ACME PQT Project ref",
      "validation_type": "DocType",
      "doctype_name": "ACME PQT Project"
    }
  ]
}
```

- **Which list.** `doctype_name` names a record type, the app's own or the shop's, with `validation_type: DocType`.
  A required sale detail is refused: it would stop every sale that does not fill it.
- **What a row reads.** The record's title, where the record type sets `show_title_field_in_link` and has a
  `title_field`, as a link in Desk does; any other record type lists names. To turn titles on later, set
  `show_title_field_in_link` in a higher version of your manifest. A blank title reads as the name, and records sharing a title read `Kitchen refit · ACME-PQT-00015`.
- **What is stored.** The record's name, always, and the sale is checked against it when it books. A customer that ticks
  *Print on the receipt* on the sale detail prints that name.
- **What it lists.** Every record of the type, in one list, as the Desk's capture window does, so finished projects
  too. Until the first record exists the till does not ask it: a cashier who opens *Sale details* reads that there is
  nothing to pick from yet, and carries on with the sale.
- **Offline.** The till does not show the *Sale details* row, and the sale completes without the value.
- **Publish it with the list.** A sale detail cannot change in place (§4): a later version cannot add a list to one
  you published without it, and must ship it under a new name.
- **When the app goes.** The list goes with it. A sale detail booked sales point at is kept switched off, its list
  cleared, and booked sales keep the name they stored (§5).

### Words in a language

Your app's screens read in the shop's language when the manifest carries your own words: one entry per language, each
a map of the text your manifest shows (a record type's name, a field or section label, a help text, a Select option)
to its words. Nothing for the shop to set up; Desk shows them to every user whose language is that one.

```json
{
  "manifest_version": 2,
  "translations": [
    {
      "language": "ar",
      "words": {
        "ACME RX Dispensing": "صرف دواء",
        "Patient": "المريض",
        "Policy number": "رقم الوثيقة",
        "The number on the insurance card.": "الرقم المطبوع على بطاقة التأمين."
      }
    },
    { "language": "es", "words": { "Patient": "Paciente" } }
  ]
}
```

- **On your record types.** A field, section or column label and a Select option of a record type your manifest
  names are written for that record type, where they read even if the shop's catalogue has the same word in another
  sense: *Patient* and *Policy number* above read your words on your form. A label you add to the shop's own record
  type (a field on Customer) is written for that record type too, so the same label on that form reads your word.
- **Across the site.** Every word is also written for the whole site, where Desk reads it with no record type: your
  record types' names (*ACME RX Dispensing* above), help texts, tab and table labels, a stored option in a list or a
  read-only form, a Desk button. A word the site already translates in that language (in a shipped catalogue, or one
  the shop set on its *Translation* screen) is left as it is and yours is not written there, so a word the site
  already shows in that language never changes, the till's included. That is why a common tab label (*Details*) or an option such as *Open* reads the
  site's word: give your record types, tabs and options words of your own where you can.
- **The shop's corrections stay.** A word the shop corrects on its *Translation* screen is the shop's from then on:
  an update and the uninstall leave it.
- **Your Desk buttons too.** A Desk button's label, its group, its dialog and its confirm sentence read through the same
  words.
- **The consent** names each language and how many words it brings, one line per language. A language is the code
  the site lists (its *Language* list: `ar`, `es-MX`); one the site does not list is refused at **Check**.
- **An update** replaces a language's words: a changed word reads new, a word left out is gone, a record type the new
  version adds reads the words too, and a language the new version drops is removed at the update (§4).
- **Uninstall** removes every word the app wrote; a word the shop set or corrected itself is never touched (§5).
- **Checked:** a language is a code (`ar`, `es-MX`), one entry per language, at least one word, every word and its
  translation text, and no markup that carries script. Your manifest's own text is the English. Messages your own services send back are yours to translate:
  a check, a Desk check and a Desk button's call carry the user's `lang`.

## 4. Updates

Bring a **higher** version: check it, read **What changes from the installed version** (added, changed and dropped
elements, and every new outside address), consent, update. An update:

- adds what is new — and takes over in place, as an install does, a sale detail or print format an earlier
  uninstall kept that the new version declares again, a sale detail's list included (a failed update puts it back as it was);
- changes in place a record type's labels, descriptions, added options, new fields and permission rows (a key left
  out is its default: `istable: 0` or an empty `autoname` written out is no change); the fields
  the manifest adds to the shop's record types; display changes; print formats; reports; workflows; notifications;
  workspaces; webhooks; and services. Each element's current form is saved on the package first; a change writes what
  the new version states, and a property it leaves out keeps the value it had — except a service, which is written
  whole: a property it leaves out (its settings, time to answer, sequence, page roles) is cleared or takes the
  product's default, and *may approve* is cleared (the shop grants it again with the consent). On a payer service the
  clearing mode stays the shop's (a manifest cannot carry one), and so does any setting the shop changed that the new
  version does not name. On a capture service the `page` the shop set stays while the new version's event still
  honours one (scan, customer select) and it still names a page placed on the till; otherwise it is dropped.
  A save rule is the other exception: a key the installed version named and the new one leaves out (its message,
  mode, factor, …) takes what a fresh install writes for it, never the old value, and so do `judge_on_change`, the
  settings-record keys (`value_from_type`, `value_from_name`, `value_field`, `roles_field`) and the four lists
  (`bypass_roles`, `states`, `locked_fields`, `scope_fields`) whenever the new version leaves them out; any other key
  neither version names stays as the shop set it;
- keeps the shop's own switch on a changed notification, webhook, workflow or save rule: one the shop switched off stays off,
  one left on stays on (a save rule the update adds follows the install's rule);
- switches off every changed service and clears its consent (the shop consents again) — except a check, at the till
  or on the Desk, that the new version declares to refuse or ask when its service is down (a check that moves onto a
  new version of its module included). It keeps the shop's switch, its consent cleared, and while it is on without a
  valid consent it is asked nothing and gives that answer: the till refuses (or asks) *"… is waiting for a manager to
  consent to it in iVendNext Desk"*, and the Desk refuses (or asks) the save or submit it checks with *"… is waiting
  for a System Manager to consent to it"*, until a System Manager ticks its consent again; the update screen says so
  on the service's line. A till that is offline goes by the checks it last loaded until it reconnects. One the shop
  had switched off stays off. ⚠ The same holds for any such check switched on without a valid consent — never given,
  or lost. Kept on, the check is saved under its own limits, so an update that would take one POS Profile past three
  till checks or ten seconds together, or one record type past three Desk checks or ten seconds, stops and is undone:
  switch one off and update again — it stays off until that POS Profile's or record type's checks fit the limits;
- keeps on what the shop had on: a changed service, Desk button or till key it had switched on and consented takes
  the update's own consent (*"consented with this update and kept on"*), at its old address or a new one, which the
  update's difference names before the shop consents; one the shop switched off or withdrew its consent from stays
  so; a till key the update adds arrives consented and on every store's till;
- creates any role the new version names that the site does not have (a role it no longer names stays until
  uninstall);
- replaces a language's words (a changed word reads new, a word left out is gone) and removes a dropped language's
  words at once ([Words in a language](#words-in-a-language));
- removes nothing else, but switches off a dropped webhook, notification, workflow, sale detail or service at once; it
  stays listed and goes at uninstall. A dropped display change (a help address included) has no switch: it stays
  as it was until uninstall;
- writes the export first (a private File on the new package).

Refused, with the reason: a lower or equal version, a dropped or renamed record type or field, a field changing
type, a removed option, a link, table or multi-select field pointing somewhere else, a record type becoming (or no
longer being) a settings record, and a change to a kind that cannot change in place (a number card, chart, dashboard, list
settings, naming rule, Connections link, event feed, fiscal reader, sale detail): ship the changed one under a new
name. To go back, ship the old content as a new, higher version.

A failed update undoes only its own changes and shows **Upgrade Failed**; the installed version still runs. The undo removes what the update added, the record type or field whose table change the database refused included (§6), so rows typed into a field the update added are lost with it
(§5, `child_rows`). If the
undo itself could not finish, **Finish** completes it. The earlier version's record keeps who consented, when and to
which summary, with status **Superseded**.

## 5. Uninstall

**Export and uninstall** writes every record of the app's own record types, with their comments and version
history, its values on the shop's records and the extension-point records as the shop left them (never a secret) to
a private File on the package, then removes the app, its words in every language included (a word the shop set
itself stays). Under `child_rows` it also writes every row of each of the app's
child record types, wherever the row hangs, grouped by `⟨record type⟩.⟨field⟩`: rows of the app's table or
multi-select field on a shop's record, of a table field the shop added that points at the app's child type, and on a
retry after a first attempt already removed the field (before 2.0.0.654 those rows were deleted with no copy). A settings
record is written as its one record, with its table rows inside it and its version history beside it; its values
leave the site with it. The export holds every child table whole, in one file, so a multi-select on a large catalogue
makes a large file. Two paths outside the uninstall remove child rows without a fresh export: **Finish** on a failed
install, and the undo of a failed update (rows typed into the update's new field before the undo); the update's own
export was written before those rows existed. The uninstall deletes those comments and that history with the
records, so the export is where they are kept; a file attached to one of the records stays among the site's files,
no longer linked to a record. The schema is left as it was found, except four kept on purpose: a sale detail that booked sales point at (kept,
switched off, adopted again on reinstall; if it listed your record type, it now reads *No Validation* with no record type, and a list the customer set on it stays), a workflow state or action another workflow uses, a partner module
(withdrawn, its record kept, §11), and the app's own user while a record of the point of sale still names it (an open
check it opened, a line it added, a kitchen ticket it moved): kept switched off, with no role, password, key or till grant (the POS user tick, its Retail Permission, shift and stores), so the
record stays workable at the till, and adopted again on reinstall, its key made again when the shop connects an app CitiXsys hosts, or by the shop (User, Generate Keys) for an app you host. A role the install
created goes too, with every permission row and user assignment naming it; one another installed app also names
stays, and goes when the last of them is uninstalled. A till key's ticks in POS Studio > Apps go with it (and a newly installed key
never inherits a tick an earlier uninstall left), so an app installed again needs a store to tick its keys again. An app hosted by CitiXsys is told it was removed (§10).

**A version consented before 2.0.0.646** (when a till key's line said *"installed switched off; it needs its own consent"*)
cannot be installed again at the same version: the summary changed, and a consent never carries over to other
content. Bring a higher version. A job queued across that release is refused at the job. Keys installed before the
release stay as they are (switched off) until a higher version installs.

**A version consented when a save rule's line said *"installed switched off"*** cannot be installed again at the same
version either, for the same reason: the line now says *switched on*, and a consent to the old words covers less than
the install now does. Bring a higher version; a package checked but not yet consented only needs its **Check** again.
Rules already installed keep the switch they have.

The uninstall drops tables and columns, which Desk cannot, so it removes **only** what both the install record and
every consented version's stored manifest name. An element outside that set refuses the whole uninstall, named, and
nothing is removed.

So the installer installs only a manifest a consented package holds; the screen and the kit's `deploy` over the API
always pass it one. A console call of `manifest_install.install` with any other manifest is refused before anything is
made, since nothing it made could ever be uninstalled. A console call with a consented manifest still installs, outside
its package, so the package record does not show it. An app put on a site from the console — with a consented
manifest, or with any manifest before this release — has a check that reads *installed here outside the install
screen* (one that failed partway reads *press Finish*, which has no package to finish), and cannot be removed from the
screen: iVendNext support removes it, with
`manifest_install.uninstall(app, export_path="<file>")` (the shop's records exported first) when a consented package
holds its manifest, and by hand otherwise (its install record's `items` lists what to drop).

## 6. Failure and Finish

Install, update and uninstall run as background jobs (queue `long`), never inside the web request. A failed install
takes back what it made and shows the reason in words — the record type or field whose table change the database
refused included (the framework commits the record before the change runs; a field left with no column failed every
later save of its record type), never a record the site held before; **Finish** removes anything left, with no fresh export
(rows of the app's child types typed in meanwhile go with it, §5). What an earlier uninstall
kept (a sale detail booked sales point at, a workflow state another workflow uses) stays the app's through a failed,
killed or later install, so the next install takes it up again, with its list if the manifest declares one. A sale detail with no sequence gets the first free one
from 900; a declared sequence another switched-on sale detail holds is refused at **Check**. If the worker died mid-job, the status stays Installing, Upgrading or Uninstalling; **Finish** takes back a
killed install (tested), completes a killed update's undo, or runs a killed uninstall again.

## 7. The API, for a sandbox

The same methods, the same checks, all `POST`:

| Method | Arguments | Answer |
|---|---|---|
| `ivendnext_mpos.api.extension_package.check` | `manifest` (the JSON) | `{ok, name, refusals, summary, summary_sha256, summary_parts, changes, mode, warnings, holders}` |
| `ivendnext_mpos.api.extension_package.install` | `name`, `summary_sha256` (echo the check's) | `{ok, name, status: "Queued", action}`, or `{ok: 0, refusals}` |
| `ivendnext_mpos.api.extension_package.uninstall` | `name` | `{ok, status: "Queued", action: "uninstall"}` |
| `ivendnext_mpos.api.extension_package.finish` | `name` | `{ok, action: "finish"}` |
| `ivendnext_mpos.api.extension_package.connect_again` | `name` (the installed version of a hosted app) | `{ok, name, connection}`: the outcome in words, never a secret |

A consent call without the summary's SHA-256, or with one that does not match, is refused: the consent binds the
summary of this exact manifest. A consent is also refused when what the update would change on the site is no longer
what the package showed (another version was installed or removed since): check it again. One version of an app acts
at a time: while one is running, or an update's undo is unfinished, the others wait for **Finish**. Read the result from the package record (`status`, `error`, `refusals`, `todo`).
Secrets reach the calling user's open Desk screen, and an app hosted by CitiXsys through its own connect (§10); over
the API, read each from its own record.

## 8. What to tell an AI assistant

"Write the manifest as data only: every field it adds to the shop's record types starts with the prefix, `version` is `major.minor.patch`, and an update
is a higher version that adds, never renames or drops a record type or field. Run the kit's checker before handing it
over. The shop installs it from the Retail Extension Package screen and consents to the summary our code writes."

## 9. Install from the App library

The **App library** (`https://library.ivendnext.app`) is iVendNext's signed list of ready-made apps, from us and our
partners. In iVendNext Desk it opens from **App library** on the *Retail Extensions* card, or from **Choose from the
library** on the Extension Packages list and on a new package. Code: `business_logic/app_library.py` · the page
`app-library` · the drawing `public/js/app_library_desk.js`. The library's own format is the library's; it is not copied here.

**The door.** Each app is a card in a grid: what it does, what it adds, and one facts line (whether it needs a Desk
user, one Desk licence each; the outside addresses it names, or *No outside address named*; who uses it). A card never
says an app sends nothing outside: any print layout can reach an outside address (§3). (The longer explanation is
the library's own text; the library owns its words.) A card's longer explanation
opens under *What it does and what you set up first*. The cards come in groups, an empty group left out: **Made for
you** (the shelf, below), **Ready to add** (library apps this site can install), **Installed** (updates, installs under
way and failures first) and **Part of iVendNext** (apps that run inside the site and are not installed here). The page
names **This site's key address** with a copy button; a partner asks the shop for that line.

**The buttons** (`business_logic/app_library.py` `_card`). An app that runs inside
the site (every door but the library's) reads *Installed · version x* when the site has it — the card's
`installed_as`, else its id, for the version too — and *Talk to your partner to add it.* with **Help** when it does
not; a newer listed version reads *Version y is ready* with **Help**. A library app reads its package record:
*Installing… This can take a minute.* with **Details** while the job runs (*Queued*, *Installing*, *Upgrading*), *The
last change to this app did not finish.* with **Details** (the package record, where *Finish* or a new install runs)
after *Failed*, *Upgrade Failed* or a refusal by the job's own re-check — a failed update keeps **Open**, since the
installed version still runs — and *Installed · version x* with **Open** (the first Desk page, `workspaces[0]`, of the
installed manifest; none when it adds no page) and **Details**; otherwise its key state, below. A first install that
failed is back under *Ready to add*.

**The key.** A free app has **Install** and needs no key: the site asks the library for its free key afterwards, as a note it never waits on. Any other app has **Enter your key**: a key iVendNext or a partner issued
for this site's key address. The site checks the key itself, in this order: its form, a signing key this release
knows, our signature (by a key allowed to sign that kind), the card's app, this site's key address, not withdrawn,
not ended, and the card admitting the kind. It then fetches the app's file, refuses it unless it is exactly the file
the signed list names and does what its card says, and hands it to the same consent screen as the package form
(one drawing, `ivn_app_library.format` and `.consent`): *Install ⟨app⟩*, the card's lead and *What it does* first,
an update's changes, then the summary in plain words under the five headings of §3, the checker's warnings, who can
install here, *Show the exact wording* (an update's changes and the summary, as stored), and the tick. **Install** stays disabled until it is ticked, and sends the summary's
fingerprint exactly as the check returned it. Nothing installs without that tick. The key is kept on the package (`library_key`), so an update or a
reinstall needs no new key while it is valid. A key that ended, was replaced or was withdrawn offers **Enter a new key** (a free app never asks for one). **Enter your key for ⟨app⟩** says a key is a short code iVendNext or a
partner gives for this site, beside the key address and its copy button.

**Where a hosted app may go.** A card with the door `library`, `access: key` and named `countries` (not `all`) says
where CitiXsys may host that app. A fresh install of it from our hosting reads the country of every company on the site
(`Company.country`, through its `Country.code`) and, with any company elsewhere, is refused under *Not done*: *CitiXsys
hosts this app only for sites whose companies are all in ⟨countries⟩, and ⟨company⟩ is not. Ask your partner to host it
for you.* A company with no till counts: the rule reads every company on the site, because the apps it binds today send
patient data from Desk checks in any company. The rule sits in the install's own check, so it holds at the card's
**Check key** and **Install**, a form's **Check** and **Consent and install**, and a pasted manifest alike. A partner's
own copy names no address on our hosting and passes; every other card is untouched; no setting turns it off. An update
that moves a partner's own copy onto our hosting is held to the same rule. ⚠ Bounds: this rule never refuses an update
of an app already on our hosting (it would leave the app and its data flow exactly as they were and block every later
fix), so the real cut-off is revoking the key, which takes these apps' site off the service; a company added after the
install is not caught by the site; a pasted manifest passes while the list cannot be read (the card's own path refuses
by itself); a shelf's list carries no `countries`, so a shelf app is held only to a public card of the same name.

**After the install.** The library stays on screen: the card reads *Installing…* and the page reads itself again every
few seconds until the package says *Installed* — a toast *⟨app⟩ is installed.*, with **Open** when the app adds a Desk
page — or the job ends without it, when the card says so and links the record. It goes on while the page is hidden,
so the toast reaches the shop on whatever screen it is on; a read the library refuses does not end it, a call that
fails does (the Desk has shown its own error); it stops at the job's own limit. A job whose worker died stays *Installing…*: **Details** opens the record,
where *Finish* ends it. It never opens the package's own form, which is the partner's and the developer's
screen. **Open** loads the page fresh, so Desk knows the record types and the page the install just added.

**The guide and the next steps** (since 2.0.0.646, `app_library.py` `_docs`, `_card`). A card's `docs` — 1 to 6 `{title, url}` in
the library's list — reach the shop as **Setup guide** beside the card's other buttons (one guide reads *Setup guide*;
several read by their own title). The address must be `https` on `docs.ivendnext.com`, `developer.ivendnext.com`, `help.ivendnext.com` or
`www.ivendnext.com` or, on the public list, on the card's publisher's own site (`web.publishers`), as the library's publish already requires; anything else
is dropped, never shown. A shelf's cards are v1 entries and carry no guide. The card's `support` field is never read: Help and Docs sit on the page. An app the site has installed adds
**Next steps** to its details (also while an update is waiting or failed — the installed version still runs): the card's `setup` steps, then the lines the install left to do (`todo`, the same text the
package record shows), each line once. The
panel opens by itself once, on the read that first shows *Installed*. A card with no `docs` shows no *Setup guide* and
nothing else changes: the page keeps its **Help** and **Docs**. Write each card's `setup` as the steps the shop does
first; they are what *Next steps* lists.

**The shelf.** A customer with apps built only for it gets a private shelf, **Made for you**, opened once with a shelf
key (the link *Have a shelf key? Open your shelf* at the foot of the page). Its apps install the same way; a package from the shelf keeps `shelf:<id>`, never the key.
**Allow.** When the App library has a shelf waiting for this site (a maker published for it, and the site has not been
handed that shelf's key), the page says *A new app is waiting from {from}: {title} {version}.* (the maker's company name, the app's title) with **Allow** and
**Not now**. *Allow* asks the App library (`POST /v1/allow` with the site's key address and the maker), which never
answers the caller with the key: it posts it back to the site's own address, to the guest call-back
`ivendnext_mpos.api.app_library.allow_delivery`. The site keeps it exactly as a pasted key, then the shelf shows under
its maker; installing still asks for consent. *Not now* leaves it waiting. The call-back believes a body only while
the site's own ask is open (the length of that one call) and a key only if it is signed for this site; only the
administrator's own request stores it. A site with no key address asks nothing, and the paste stays for every site.
⚠ Bound: the App library's door has no login, so whoever knows a site's address can spend its 30 asks an hour, or
ask for the key while the administrator does, which turns that *Allow* into *ask the maker for the key*; whoever holds
a real key for the site and posts it inside the administrator's ask does the same; a listing posted by anyone inside a
listing ask blanks *Made for you* for that one read. Nothing is ever stored that way.
An app hosted by CitiXsys on the shelf also brings its own App library key for this site, so it connects like a
library app (§10): its entry carries `app_keys`, one key per site the shelf serves, by key address
([sample](../extension_contracts/samples/shelf_entry/hosted_app.json)).
The site takes only the key under its own address, checks it as it checks a pasted key (the withdrawn list is the
App library's own), and keeps it encrypted on the package; any other site's key is neither kept nor sent. A missing
or refused key never stops the install: the consent says why the app will not connect itself, and a new version
that carries its key is the way to connect it. If the App library's list cannot be read or checked, the app is not
taken, and the page says why in the list's own words (try again later, or ask iVendNext support for a fault that lasts). ⚠ Bound: every site a shelf serves holds that shelf's key, and whoever
holds it can read the shelf's list — so one customer's test site can read its live site's app key (only that
customer's or that maker's own sites, never another's).
A site keeps one key **per shelf**: a customer served by two makers opens both shelves, and each shows as its own
section, headed *Made for you by {maker} · {customer}*. A key for a shelf already open replaces only that shelf's key.
An app is taken and updated only with the key of the shelf it came from, never another shelf's: when two shelves
list the same app (a maker's preview shelf beside its customer shelf), the shelf it was installed from offers its
updates and the other's card just says it is installed (to take it from the other shelf, uninstall it first).
**Remove** on a section is how a shop stops working with that maker without asking iVendNext: after a question, the
site forgets that shelf's key and its section goes; every other shelf stays. Apps already installed from it stay and keep working, and their
packages stay under *Extension Packages* (their cards leave the library page with the section); their updates stop
until that shelf's key is entered again — a version checked before *Remove* is refused at consent, and a job queued before
it installs nothing; an app uninstalled from the shelf is not installed again until then either. The highest list number the site has seen for each shelf is kept, so a key pasted again is never
served an older list. *Remove* shows on a refused shelf too (moved, ended, withdrawn, or a key the site can no longer read), and waits while one of the
shelf's apps is installing; a refused shelf shows its id, so two refused shelves can be told apart. Another maker's key
never re-opens a removed shelf's updates: each version is checked against its own shelf's key. The one key a site kept
before each shelf kept its own moves to its shelf the first time the page, a consent or an install job reads it; a key
that cannot move (the library refuses it, or the site cannot read it) shows as a refused shelf whose *Remove* sends
the id `old`, and opens no shelf's updates.

**The refusals** say what to do next: check you copied all of the key, ask whoever gave it to you for a new one, ask
for a key for this site's key address, ask your partner or iVendNext, or try again. A site whose own name is not a
public one (a self-hosted test box such as `usdbeta.local`) uses the host of its `host_name` setting; with neither
public it takes no key.

**Who may use it.** Every action asks for the package record's own permission, as everything on this page does. The
page itself ships with System Manager; a shop that grants the package permission to another role adds that role to
the page in *Role Permission for Page and Report* to show it the link.

| Method (all gated) | Arguments | Answer |
|---|---|---|
| `ivendnext_mpos.api.app_library.library` | none | the key address, each card and its state, the shelves (one section per shelf) |
| `ivendnext_mpos.api.app_library.take` | `app`, `key` (or none: the stored key), `shelf` (a shelf's id, for an app on that shelf) | `check`'s answer, or `{ok: 0, refused, words, detail}` |
| `ivendnext_mpos.api.app_library.free_key` | `app` | the same |
| `ivendnext_mpos.api.app_library.open_shelf` | `key` | `{ok}` or a refusal |
| `ivendnext_mpos.api.app_library.remove_shelf` | `shelf` (the shelf's id, or `old` for the site's key from before each shelf kept its own; never a key; `POST`) | `{ok}`: that shelf's key is forgotten; installed apps stay |

The library's call-back, `ivendnext_mpos.api.app_library.confirm` (`POST`, no login, rate-limited), answers only for a
request this site made in the last two minutes, once.

## 10. An app hosted by CitiXsys: connect, goodbye and Connect again

An app whose outside addresses (`allowed_urls`) are on `ivendnext.app`, or any name under it, runs on CitiXsys
hosting and serves many shops. It learns each shop from the shop's own site:

- **After the install, after an update, or when Finish completes one**, the site calls the app once:
  `POST https://<the app's host>/ivendnext/connect`, unsigned, with the header `X-iVendNext-Site: <this site's key
  address>` and the body `{"key", "site", "secrets"}`. The key is the App library key the app was taken with; the app
  checks it (signed by iVendNext, for that app, for this site). The secrets are every one the install made, each read
  from its own record at that moment, by the names the partner kit uses: a till key `<app>:<key>`, a Desk action's
  service `<app>:sub:<key>`, a webhook by its name. A hosted app has one address: a manifest naming more than one
  address on `ivendnext.app` is not connected (the key and the secrets would reach every one of them).
- **The app's own user's key** (the user the install made for its event feed, `<app>@integration.invalid`) is
  made at the first connect, once, and sent as `user:<email>` → `<api key>:<api secret>`; a key the shop makes on
  it later (User → Generate Keys) is the one sent after that. **Any other user's key** (a fiscal reader's writer,
  or a user the shop named on a feed before the install made one) is sent once the shop has made that key; the
  install never makes it. Make the key, then press **Connect again**. **Hosted app** names each user whose key was
  sent. The site's own Administrator's key is never sent, nor a disabled user's.
- **At uninstall**, the site calls `POST …/ivendnext/disconnect` with `{"key", "site"}`, after the app is removed, to
  the hosted address the installed version names. If the app cannot be told, **Hosted app** says so: tell the app's
  maker, and make new API keys for any user whose key it was sent (the button went with the app).
- **Every other call to the app** — a till key, an extension point, a webhook — carries `X-iVendNext-Site` too, so the app checks
  it with this shop's own secret. A webhook gets the header when the install makes it or an update moves it onto
  CitiXsys hosting. ⚠ A webhook made before this release does not: update the app, or reinstall it.

**Hosted app**, on the package, says what the app answered: connected, or why not. Nothing the app answers can fail
or undo an install, an update or an uninstall. When the app could not be reached or refused, the install stands and
**Connect again** (installed version, hosted app) makes the same call with every secret read afresh — after the app
is back, after a secret was rotated, or after an integration user's key was made. The app keeps the previous set
for one connect while the shop moves over, so to stop a leaked secret working, press **Connect again** twice (not while this site's key is withdrawn: no call is made).

No call is made, and **Hosted app** says why, when this site holds no App library key for the app (a manifest pasted
by hand for an app never taken from the library; a pasted update of a library app uses the newest key this site
holds for it), when the newest is a *Made for you* shelf's and its shelf sent no key for this site that this site
accepted (§ The shelf; a newer version taken from the shelf decides by its own entry, a pasted update keeps the
shelf's key, and a manifest pasted over a version not yet consented to drops the key it came with), when the site
has no public key address, or when the address is not https. Give such an app this site's
secrets by hand. When the installed version cannot be connected for one of these reasons, its uninstall sends no
goodbye and the field is cleared. ⚠ Bound: the goodbye goes to the address the installed version names, so an app
connected by an earlier version at another hosted address is not told by this site — nor is a shelf app connected by
an earlier version when the version installed now came from the shelf without its key.

The site checked the key's end date and withdrawal when the app was taken from the library or its shelf. Every connect
(the install's, an update's, *Finish* and *Connect again*) reads the signed list, in a copy at most 10 minutes old, and
never calls the app with a key that copy withdraws, on any hosted app: *Not connected: this site's App library key was
withdrawn by iVendNext, so ⟨host⟩ was not called. Ask whoever gave it to you.* A list it cannot read cuts nobody off,
and an uninstall's goodbye still goes. No connect checks the end date, and the app checks only the signature, the app
and the site (guide 14b), so a connect posted by hand with a withdrawn key still reaches it. ⚠ Bound: a site given a new
key after a withdrawal cannot enter it on the version it runs (a check refuses the same version). The new key goes in
with the next version the library lists, or by uninstalling and installing again. A withdrawn key cannot be reissued;
only a key still in force is reissued under its own id.

⚠ What we keep on purpose: the App library key is the credential, and the package screen shows it to whoever reads the
package (a shelf app's own key is the exception: it is kept encrypted and never shown). Whoever holds it can connect as this shop and replace its secrets at the app; the shop's next install or
Connect again connects it back, unless that key is withdrawn. A site whose private-hosts setting (`mpos_remote_app_allow_private`) allows a private
address lets the connect reach one, as every partner call does (a test bench); no other setting changes it. A failed
connect writes no Error Log: the error tracker would receive the call's body with it; the field says what happened.

## 11. A certified module in a package

A package can carry a partner module our certify service signed, for an extension point that runs modules (the
[check before payment](partner_check.md) and [pricing](price.md)), with the service that runs it.

```json
"extension_modules": [
  {"key": "member_price", "point": "price", "version": 1, "metered": true,
   "sha256": "2950a196…", "certificate": "9zXN…", "wasm": "AGFzbQEAAAA…"}
],
"extension_subscriptions": [
  {"key": "member_price", "point": "price", "label": "Member price", "transport": "wasm", "module": "member_price"}
]
```

- **What it carries.** `point`, `version`, `metered`, `sha256` and `certificate` are the module's certificate file as
  our certify service gives it; `wasm` is the module's bytes in base64; `key` names it in the manifest. A module may
  give a `partner_name`; with none it takes the manifest's publisher, else its prefix, as a service does (plain text,
  no space at either end, and one module per partner and extension point in a manifest). A module's
  service is an `extension_subscriptions` entry with `transport` `wasm` that names the module's key: same extension
  point, same partner, no address and no secret. The pricing extension point takes a module only.
- **What the checker checks** (in the kit and at the shop): the key, an extension point that runs modules, a version
  that is a whole number from 1, the meters, a certificate that reads as a signature, at most 256 KB of module, and
  that the bytes are the ones `sha256` names. It cannot check the signature: the shop does, when it installs the
  module, with the key it holds, and refuses a module our certify service did not sign in the module's own words, or
  one iVendNext has recalled (*"recalled (our certify service withdrew this module's certificate)"*).
- **What the consent says.** One line for the module (its version, its partner, its SHA-256, a sealed program that
  runs inside the shop and only through a service you switch on, withdrawn by an uninstall) and one for its service:
  where it runs, what it may do, that nothing is sent outside the shop, and for pricing that the most it may take off
  stays 0 until you raise it.
- **What the install makes.** The module and its service are the last things a fresh install makes. The module is the same record
  a System Manager adds by hand (**Retail Extension Module**, its file private and attached to it), admitted by that
  record's own checks. Its service arrives switched off, consent not given, and a pricing service's limit at 0: a
  manifest never carries the limit (`max_discount_percent` is refused). Installing a package that carries a module
  needs the module record's own create permission (a System Manager's by default), beside the package permission;
  switching its service on is the System Manager's, on the service's own record.
- **A version is used once.** A module's record is never deleted: its SHA-256 and the time it was in use stay, so a
  sale drained later is checked against the version its till ran. So the check refuses, before anything is made, a
  version this site already had (even one an uninstall withdrew), a module whose bytes were added before, and a module
  of the same partner and extension point that this app did not add (a package never replaces one). The words say the
  partner owes a higher version.
- **Uninstall** withdraws the module and keeps its record (its file goes 30 days later), deletes its service as it
  deletes any service, and says on the package what it kept. A sale a till made offline with the module before the
  uninstall goes to review when it drains. An uninstall, a Finish or an update of an app holding a module needs the
  module record's write permission too. Installing the app again needs a higher version of the
  module.
- **Update.** A higher version with a new build is added beside the old one, which it replaces: every service that
  ran the old version now runs the new one, switched off with its consent cleared, so the shop reads it again (a
  pricing service keeps the limit the shop set). The same version, a lower one, the same bytes, another extension
  point or another partner name is refused. A failed update puts the old version and its services back; the new
  version it added is spent (withdrawn, listed), and the package's error says so.
- **A failed install** removes what it made. A module refused at the install leaves nothing. With two modules, one
  refused after the other was admitted spends the admitted one (withdrawn, its record kept), and the package's error
  says so.
- **Size.** A module rides inside the manifest. The install screen takes a module up to the till's 256 KB, but the App
  library serves a manifest of at most 256 KB, so a library app keeps its whole manifest, the module's base64 included,
  under that (a module of about 190 KB).

## 12. A connection point's secret and its test

A connection point is a record an install hands a secret to, with an address: a service (Retail Extension Subscription),
a till key (Retail Remote App Key) or a webhook an install made. A module service has no address and no secret, and a
webhook made by hand is not a connection point, so neither has these buttons.

- **Shown once on consent.** When consent is saved on a service or a till key, its secret is shown once with *Copy*. An
  app hosted by CitiXsys needs nothing copied: the site shows what the app's connect answered, as on its package (§10).
- **Copy secret**, beside the masked secret on the record, copies it and says *Copied*. It needs **write** on the record:
  a System Manager by default, and anyone the administrator grants it to in Role Permissions Manager.
- **Test connection**, on the record, on each row of its list and in the list's *Actions* for the ticked rows. It needs
  **read** on the record. It runs before consent and on a record that is switched off, because it carries nothing consent
  covers. It writes no Error Log and no extension log row.

**What your app receives.** One `POST` to the record's address, signed exactly as a real call of that kind, with the extra
header `X-iVendNext-Test: 1` and the body `{"test":1}`: no sale and no record. A service's and a till key's call is signed
over the timestamp and the body ([the signature](remote_till_key.md)); a webhook's over the body alone, in
`X-iVendNext-Webhook-Signature`. The marker is not signed, so a test proves the handshake only, never your app's logic.

**What your app should answer.** Verify the signature first, as on any call. Then, if the marker is there, do no work and
answer HTTP 200 with `{"test":"ok"}`. Check the marker before you validate the body: a test has no `point` or `context`.
An app that does not know the marker needs no change: it is read by its status, as in the table.

| Your app answers | The site says |
|---|---|
| 2xx with `{"test":"ok"}` | **Passed**: reached, signature accepted |
| any other 2xx | **Passed**: reached and accepted; the app did not say it knows the test |
| 401 or 403 | **Failed**: the app did not recognise the site's secret, and what to do |
| 404 | **Failed**: nothing answered at this address |
| a 3xx, any other 4xx, a 5xx | **Inconclusive**: reached, answered HTTP n; read the app's log (a real call fails on any of these) |
| 2xx too long or cut short | **Inconclusive**: reached, but the answer could not be read |
| nothing, within the record's time to answer | **Failed**: no answer within n s |
| no connection | **Failed**: not reached |
| a webhook on `http://` | **Failed**: the address is not https (it is not called) |

A sandbox or a tool can test all of an app's points at once: `GET /api/method/ivendnext_mpos.api.extension_package.test_connection?app=<app>`
returns one `{key, plain, outcome, words}` for each. It needs read on each record, and refuses the whole test otherwise.
