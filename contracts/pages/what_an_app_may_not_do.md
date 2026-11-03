<!-- Source: ivendnext/iVendNext_PWA docs/extending/what_an_app_may_not_do.md @ cff85a09aa4d, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# What an app may not do

An app may do anything the shop's administrator can do in Desk: a workflow that approves and
submits a Purchase Order, a notification when one is submitted with its print attached, a numbering
rule on Material Request, list columns, a required field, a relabelled field. The install refuses
only what would:

- **A** book a wrong money, tax, stock or fiscal figure;
- **T** stop the till saving a sale, the day's close or a new customer at the counter;
- **B** send the shop's data somewhere the consent does not show the shop;
- **C** let someone act as someone else, code running in the shop's saves or in a viewer's browser included.

Two more kinds are not refusals of what an app does: **S**, the installer cannot read or carry it
out as written (a missing name, a record type the site does not have, a name another app holds),
and **K**, the App library's commercial rules (a paid app's key, the private shelf's key).

The till's own records are POS Invoice, POS Opening Entry, POS Closing Entry, POS Invoice Merge
Log, the records the till's booking writes (Sales Order, Sales Invoice, Delivery Note, Payment
Entry, Journal Entry, Serial and Batch Bundle, Repost Item Valuation, Stock Reservation Entry,
Store Expense, and the ledgers), Customer, Contact and Address, and what the till writes inside its saves (Manager Override Log,
Loyalty Point Entry, Coupon Code, Retail Card Terminal Txn, Retail Partner Code), with their rows. Everything else the framework and the product
check when the installer saves it, in their own words.

## The list

Every refusal on the install path is on this list: its file, the function it is in, how many
refusals that function holds, the kinds it serves, and why. A build check counts them, so a
refusal added anywhere else fails the build.

| File | Function | Refusals | Kind | Why, and who meets it |
|---|---|---|---|---|
| manifest_check | `validate` | 7 | A B C S | The manifest is an object with an app name, prefix and version the installer keys on (S); a prefix that starts like a flag the engine reads (A); server and client scripts, web pages and templates (C); outside addresses that are not plain, which the consent could not show (B). A partner meets each once, writing the manifest. |
| manifest_check | `_V.list_of` | 1 | S | A kind is a list of entries the installer reads one by one. A partner's typo. |
| manifest_check | `_V.no_script` | 1 | C | Markup carrying script in any text Desk shows as written runs in the browser of everyone who opens it, the administrator included. |
| manifest_check | `_keyed` | 1 | S | Each entry names what the installer reads it by (its name, record type, address). A partner's typo. |
| manifest_check | `_fields` | 5 | A C S T | A field the app adds to the shop's record type carries the app's prefix, so it is never read as one of the engine's flags (A); a required, unique or limited field on the till's own records stops the sale or the new customer (T); a default or precision on a ledger or a record type that posts changes a posted figure (A); an HTML field and a display condition in JavaScript run script in Desk (C); a field is an object (S). |
| manifest_check | `_limits` | 1 | A | A fiscal reader's result field keeps the writer level the reader gives it, so only the fiscal writer writes the authority's answer. |
| manifest_check | `_property_setters` | 2 | A C T | The same field rules as `_fields` for a change to the shop's own field, and the sale's own numbering (A, T); a display condition in JavaScript (C). |
| manifest_check | `_print_formats` | 5 | B C | A script print format (C); a print that loads from outside, runs raw database queries, builds an address from the record, or reads records past the viewer's rights, because a printed or shared receipt can carry the shop's data out (B). |
| manifest_check | `_notifications` | 8 | A B C T | Mail and the in-app bell only, to the shop's own people by role or by a field of the record, which the consent names, never an address the manifest names, a field the app gives a default address, or a file a field names (B); on the till's own records only a reminder Days Before or After a date, because any other event runs inside the till's save (T); a condition is a plain comparison of the record's fields, and the subject and message call nothing, because all three are evaluated with a Server Script's globals inside the save (C); a field set after the alert is the app's own, because the record is saved after it (A). |
| manifest_check | `_workspaces` | 4 | C | A custom block, a shortcut's stats filter, a label with markup and an icon that is not an icon name all run or write markup in the viewer's browser. |
| manifest_check | `_sale_attributes` | 1 | T | A required sale detail stops every sale on every till that does not fill it. |
| manifest_check | `_webhooks` | 3 | B T | A webhook calls an address the consent shows, and sends the thin body, because a body of its own is a template that can read any record without rights and send it there (B); a condition on the till's own records runs inside its save (T). |
| manifest_check | `_reports` | 3 | B C | A query report runs SQL over the whole database and a script report runs Python (B, C); the sort order is written into the report's query (C). |
| manifest_check | `_roles` | 1 | B | Guest and All open the app's records to people outside the shop's staff. |
| manifest_check | `_workflows` | 2 | A T | A workflow on the till's own records holds the sale for an approval nobody at the counter gives (T); a state writes only the app's own field, because it writes and then submits, so a warehouse, tax or discount field would post a figure nobody chose (A). |
| manifest_check | `_naming_rules` | 1 | A | The sale's own records are numbered by the shop's series, which its books and tax authority read. |
| manifest_check | `_endpoint` | 1 | B | A till key or a service calls an https address the consent shows. |
| manifest_check | `_extension_subscriptions` | 1 | A | The most a module may take off a line is the shop's to set. |
| manifest_check | `_payer_settings` | 1 | A | A payer's clearing account is on the shop's books, so the shop picks it. |
| manifest_check | `_desk_actions` | 1 | S | A Desk action names one of the app's own Desk action services, which the installer makes first. |
| manifest_check | `_fiscal_readers` | 4 | A | The fiscal result fields sit at their own permission level, on the sale, in text the receipt prints the authority's QR and seal from. |
| manifest_install | `_site_refusals` | 6 | S | A record type, field, print format or language the site does not have, or a name already on the site that another app made. Met when installing on a site that lacks something. |
| manifest_install | `_site_refusals_v2` | 8 | C S | The same for the newer kinds, and a site whose till app predates an extension point (S); another app's fiscal writer role, which reaches the sale through the shop's grants (C). |
| manifest_install | `_role_refusals` | 1 | S | The app's own fiscal writer role is made by its fiscal reader, after everything else that could name it. |
| manifest_install | `_module_refusals` | 1 | C S | A package never replaces a module another app added (C); a module's version is used once (S). |
| manifest_install | `_width_refusals` | 1 | S | The record type has no room left in the database for the fields the app adds. |
| manifest_install | `install` | 2 | B S | Only a package the shop consented to is installed, so the consent covers it (B); an app already installed is uninstalled first (S). |
| manifest_install | `uninstall` | 3 | S | Only an installed app is uninstalled, its records exported first, and every element it made removed. |
| manifest_install | `export` | 1 | S | Only an installed app's records are exported. |
| manifest_install | `_apply_modules` | 1 | C | A package never replaces a module another app or the shop added, checked again at the insert. |
| manifest_install | `_free_level` | 1 | S | A field limited to roles needs a free permission level on its record type, and all nine are in use. |
| manifest_install | `_make_user` | 1 | S | The site's licence has no room for the app's own user. |
| manifest_install | `_one_role` | 1 | C | The app's integration user would reach more than its one role, through rights this site gave it. |
| extension_package | `check` | 2 | B S | A manifest that cannot be read (S); a consent never carries over to other content under the same version (B). |
| extension_package | `install` | 7 | B S | The package's state, and the consent to exactly what the screen showed (B, S). |
| extension_package | `run_job` | 2 | B S | The package left the shelf, or the site changed since its check (B, S). |
| extension_package | `uninstall` | 1 | S | Only the installed version is uninstalled. |
| extension_package | `finish` | 2 | S | Finish runs only for a package stopped part-way. |
| extension_package | `connect_again` | 2 | S | Only an installed app CitiXsys hosts connects. |
| extension_package | `_app_busy` | 1 | S | Another version of the app is still running or its update was not undone. |
| extension_package | `_evaluate` | 3 | S | An earlier run did not finish; a version not higher than the installed one; an app installed outside the install screen. |
| extension_package | `_field_refusals` | 5 | S | An update cannot carry a field's stored values across a change of type, options, target, required or unique, or its roles: ship a new field. |
| extension_package | `upgrade_plan` | 12 | S | What an update cannot change in place (the prefix, a module's partner or version, a service's transport, a record type's shape): ship it under a new name. |
| extension_package | `_module_rights` | 1 | C | Adding a partner module needs the right to create one, a System Manager's by default. |
| extension_package | `_withdraw_rights` | 1 | C | Withdrawing one needs the right to write one. |
| extension_package | `_outside_the_card` | 1 | K | CitiXsys hosts the app only for the companies its card names. |
| extension_package | `name_package` | 1 | S | The pasted file names its app and version, which name the package's record. |
| extension_package | `validate_package` | 2 | B S | A file the shop consented to cannot change, and the record's name is the app and version. |
| extension_package | `refuse_delete` | 1 | B | A consented package is kept as the shop's record of what it agreed to. |
| app_library | `_get` | 1 | S | The App library cannot be reached. |
| app_library | `_list` | 2 | C S | The library's list is not the signed list it should be. |
| app_library | `catalogue` | 4 | C S | The same, for the catalogue. |
| app_library | `_raise_catalogue_serial` | 2 | C | An older catalogue never replaces a newer one. |
| app_library | `_signature_step` | 3 | C | The library's signature is checked against its own key. |
| app_library | `check_key` | 8 | K | A paid app's key: its form, app, site, end date and whether it was withdrawn. |
| app_library | `manifest_for` | 5 | C | The manifest is the one the library's card signs. |
| app_library | `take` | 3 | K | An app is in the library and installs from here, and a paid app's key comes first. |
| app_library | `free_key` | 6 | K S | A free app's key request, and the library's answer. |
| app_library | `check_shelf_key` | 4 | K | The private shelf's key. |
| app_library | `shelf_list` | 9 | C K | The private shelf's signed list. |
| app_library | `_raise_shelf_serial` | 2 | C | An older shelf list never replaces a newer one. |
| app_library | `_old_shelf` | 1 | K | A shelf key that moved. |
| app_library | `_ask_library` | 1 | S | The library cannot be reached. |
| app_library | `_allow_refused` | 1 | K | The library's answer to a request to allow an app. |
| app_library | `allow` | 4 | K | A request to allow an app on this site. |
| app_library | `take_from_shelf` | 5 | K | An app on the private shelf. |
| app_library | `library` | 1 | S | The App library screen needs the right to open it. |
| app_library | `_shelf_section` | 2 | K | The private shelf's section of the library. |
