# Make one of our apps your own: copy, change, deliver, host

Your customer likes one of the App library's apps but works differently. This recipe turns that app into yours: your company's name on it, your customer's change in it, delivered to your customer's site, at your price. It is for an iVendNext Partner, or a licensed customer's IT team, who builds for a customer. Why it is worth doing, what it costs and what stays yours: [Build your business on iVendNext's apps](../site/pages/business.md).

**Start from:** an app iVendNext lists in the App library that is built from a sample in this kit; its page in the App library links that sample. iVendNext's own products there (iVendNext POS, its payment apps, its connectors) are not kit samples and are not copied. **Worked example:** `samples/s2_bins/`, the code of *Bin locations*, made into *ACME Bins* for a chain that keeps stock in zones.

## First: does the customer need a copy?

| The customer wants… | Do this | Your work |
|---|---|---|
| what the app does, with their own values (thresholds, stores, words) | Install the app from the App library and set its settings and records | Set-up and training |
| a fix, or a setting every retailer with the need would want | Tell us with the [feedback forms](../feedback/README.md): it may become part of the standard app, at no cost to your customer | Set-up, and your time saved |
| it to work their own way: a field, a rule, a screen, a link to their own system | **Make it your own**, below | Your app, your price |
| something no app does yet | Build it from the nearest sample, the same way | Your app, your price |

## What the customer gets, in the worked example

The chain keeps stock in zones: a cold room, a cage, the shop floor. It wants each bin to belong to a zone, and when the cashier presses **Where is it?**, the answer names the zone with the bin:

*"CHARGER-USBC: shop floor MIYO-B12 (3), cold room; CASE-PHONE: back room MIYO-R03 (20), cage, fetch it"*

*Bin locations* has no zones. *ACME Bins*, your copy, does. Everything else works as before.

## Steps

1. **Set up your company once,** on [My apps](https://developer.ivendnext.com/apps): sign in with GitHub, press **Set up my company**, give your company's name as retailers see it and take the first word we suggest (`acme`). It is yours at once. Every app you name under your word is yours, and no other company can take a name under it ([Build your first app](../site/pages/first_app.md), step 1).

2. **Make the app from the sample.** From any folder that is a git repository or an empty one (or **New app** on My apps):

   ```bash
   ivn new acme_bins --from s2
   cd apps/acme_bins
   ```

   It makes `apps/acme_bins`, a copy of the sample under your names, its code, tests and README included:
   - its record types: `PP BLN Bin` → `ACME BINS Bin`;
   - its field on the retailer's items: `pp_bln_default_bin` → `acme_bins_default_bin`;
   - its role: `PP Integration` → `ACME BINS Integration`;
   - its till key and its workspace.

   The folder holds a `LICENSE` to replace with your own and a `THIRD_PARTY.md` with the notices of what it was made from. Your repository can stay private.

3. **Give it a feed.** The app is the till key's service alone, as *Bin locations* is, and the service reads with the app's own user. The feed is what gets your service that user: the install makes the app's own user and names it on the feed, and the retailer's site hands your service its key. Add it to `manifest.json`:

   ```json
   "registered_applications": [{"name": "ACME BINS Bins feed",
     "description": "the Where is it? service reads the bin records", "events": ["ACME BINS Item In Bin"]}]
   ```

4. **Make the change your customer needs.** For zones, three small changes:
   - in `manifest.json`, a **Zone** field on `ACME BINS Bin`:

     ```json
     {"fieldname": "zone", "fieldtype": "Data", "label": "Zone", "in_list_view": 1,
      "description": "Where in the store this bin is: Cold room, Cage, Shop floor."}
     ```

   - in `service/bln/service/where.py`, `bin_rows` reads each bin's zone from the bin itself, so a bin's zone shows at once, on records old and new:

     ```python
     bins = sorted({r["bin"] for r in held if r.get("location") in kind_of})
     zone_of = {b["name"]: b.get("zone") for b in rows(f"{prefix} Bin", ["name", "zone"], [["name", "in", bins]])} if bins else {}
     return [{"item": r["item"], "bin": r["bin"], "qty": r["qty"], "kind": kind_of[r["location"]], "zone": zone_of.get(r["bin"])}
             for r in held if r.get("location") in kind_of]
     ```

   - in `service/bln/core.py`, the answer names the zone after the bin:

     ```python
     def _zone(row: dict) -> str:
         return f", {row['zone'].strip().lower()}" if (row.get("zone") or "").strip() else ""
     # … f"{code}: shop floor {floor[0]['bin']} ({_qty(floor[0]['qty'])}){_zone(floor[0])}{more}"
     ```

   The sample's test `test_the_shop_is_read_with_the_apps_key_and_only_read` (`tests/bln/test_where.py`) pins the records the key reads: add the third read, `ACME BINS Bin`'s, to its list. Add a test of your own for the zone. Then set your own `title` (*ACME Bins*) and `description` in the manifest.

5. **Check it, then try it on a site.** On My apps, **Try on** *your site* (**Change** picks another, or adds one). In a terminal:

   ```bash
   ivn check
   ivn try
   ```

6. **Publish it.**
   - **To one customer:** on My apps, **Publish**, then **To a customer**. In a terminal:

     ```bash
     ivn publish --to chain-a-test.ivendnext.com --to chain-a.ivendnext.com
     ```

     It puts the version on that customer's own shelf and prints the message to send their administrator, with the key in it. A shelf for one customer needs no approval by us. Their administrator opens **App library**, presses **Open your shelf**, pastes the key, presses **Install** on your app, reads what it will change, ticks **I agree** and presses **Install**, first on their test site.
   - **To every retailer:** on My apps, **Publish**, then **To everyone**, or `ivn publish --public`. You are asked once for its card. Its first listing waits for one approval by us; your company is then its maker in the App library.

7. **Run its service.**
   - **On iVendNext App Hosting** (for one customer or for every retailer): publishing orders it and asks for the plan the first time. Your app answers at `https://acme-bins.ivendnext.app`. Each retailer's site connects itself after its install, whether the retailer took it from the public list or from its *Made for you* shelf, and hands your service the key of the app's own user (step 3); the retailer presses **Connect again** on your app's record only if the site could not reach the app, or a key was lost or changed. An app that only answers presses, listed on the App library's public list, carries no hosting charge.
   - **On your own server, for one customer:** put your service's address in the manifest in place of the sample's, and set the retailer's three values (`service/bln/service/where.py` names them):
     - `IVN_POINT_SECRET`, the till key's secret, which the install shows once in Desk, on the till key's record;
     - `IVN_SHOP_URL`, the retailer's address;
     - `IVN_SHOP_KEY`, the API key of the app's user, which the retailer makes with **Generate Keys** on that user.

8. **If the customer already uses our app, move its records.** Install yours beside ours: the two apps never share a name. Then copy every record across:

   ```bash
   BASE=https://<the customer's site> KEY=<key> SECRET=<secret> python3 tools/deploy/copy_records.py ivendnext_bln acme_bins            # shows what it would copy
   BASE=https://<the customer's site> KEY=<key> SECRET=<secret> python3 tools/deploy/copy_records.py ivendnext_bln acme_bins --write    # copies
   ```

   It copies in the order the links need (locations, aisles, bins, then what is in each bin), with each record's table rows, and moves each item's default bin into your field, never over a value already set in yours. Bin locations names its records from their own fields (a bin by its code), so you can run it again at any time: it copies only what is new. Check the counts it prints, then uninstall our app from its package record. Its uninstall also keeps a copy of every record in a file.

9. **Keep it running.** Each version of what your app relies on (an extension point's contract, an API call, the manifest format) is served for 12 months after its successor ships, so your customer's upgrades keep your app running. Read [the kit's changelog](../CHANGELOG.md) before each release of yours.

10. **Sell it again.** The next customer with zones gets *ACME Bins* on its own shelf. When it suits many retailers, list it once for every retailer (step 6).

## Good to know

- **A site can hold several companies' shelves.** Each opens with its own shelf key, and your app takes its updates only from your shelf.
- **Taking our improvements.** Your copy changes only when you change it. `ivn status` says when a sample has a newer version, and `ivn take s2` takes it, keeping what you changed.
- **A copied app keeps the extension points it uses.** A copy of a till key app is a till key app: the doors, their limits and what the retailer consents to are the same as the original's (each sample's README says them).

## Technical notes

- **What `copy_records.py` reads and writes:**
  - It reads, from the site's own record of each install, the record types each app made and the fields each added to the retailer's records.
  - It matches each record type and field by its name after the prefix (`IVENDNEXT BLN Bin` → `ACME BINS Bin`).
  - A field the first app has and yours does not is named, never guessed. A cancelled record is not copied. It deletes nothing, on either side.
  - A record whose name comes from its own fields (a bin from its code) keeps its name, and a second run skips it. A record the site names itself (a number or a random name) gets a new name, and each link to it follows; such a record type is copied only into an empty one of yours.
  - The key is a System Manager's.
- **Tested:**
  - **The worked example on a demo site:** *Bin locations* held 10 records and an item's default bin, and *ACME Bins* was installed beside it; *ACME Bins* in the form of step 3 installs and uninstalls cleanly.
    - The copy moved every record, field for field, and the item's default bin. A second run copied nothing.
    - With zones set on two bins, the service answered as above.
    - After *Bin locations* was uninstalled, *ACME Bins* still held every record.
  - **The hosting package:** built for `acme-bins.ivendnext.app` and imported as the hosted function imports it, it answers `/health` and refuses an unsigned till call.
