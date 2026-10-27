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

1. **Register your company once.** Through Help (`https://help.ivendnext.com`) or your account manager, send your company's name as retailers see it, the first word you want for your company (`acme`), the line `python3 tools/publish/publish.py keygen` prints, and your `recipient.pem`. Every app you name under your word is yours, and no other company can take a name under it ([Publish your app](../site/pages/publish.md), step 2).

2. **Start your repository from a copy of the kit, and copy the app into a folder of its own.** A sample's service uses the kit's app template (`tools/app_template/service`: the handshake with each retailer), so your app sits inside a copy of the kit, two folders down:

   ```bash
   git clone https://github.com/ivendnext-developers/partner-kit.git acme-apps
   cd acme-apps
   git remote rename origin kit            # the kit stays a remote; push to your own repository as origin
   mkdir -p apps && cp -r samples/s2_bins apps/acme_bins
   ```

   Keep the kit's `LICENSE` and `NOTICE` for the parts you copied (Apache 2.0). Put your own licence for your changes beside your app, and list the components your app ships in `THIRD_PARTY.md`. Your repository can stay private.

   **Shortcut for steps 2 and 3:** `python3 tools/manifest/start.py s2_bins --prefix "ACME BINS"` makes `apps/acme_bins` from the sample, renames it and also rewrites the code, tests and README that the rename below only lists, and finishes only when no copy of the sample's prefix, app name or folder is left and the kit's checks pass (add `--test` to run the copied tests). It needs your repository made from the kit, as step 2 sets up. The steps below are what it does for the manifest.

3. **Rename it to your company's prefix, in one command.**

   ```bash
   python3 tools/manifest/rename.py apps/acme_bins/manifest.json --prefix "ACME BINS"            # shows what changes
   python3 tools/manifest/rename.py apps/acme_bins/manifest.json --prefix "ACME BINS" --write    # writes it
   ```

   It renames every name the app creates on a retailer's site:
   - its record types: `PP BLN Bin` → `ACME BINS Bin`;
   - its field on the retailer's items: `pp_bln_default_bin` → `acme_bins_default_bin`;
   - its role: `PP Integration` → `ACME BINS Integration`;
   - its till key and its workspace.

   It renames the hosting order beside it as well (`app.json`). Your app's address name becomes `acme-bins`, and its paths point at `apps/acme_bins`. It then runs iVendNext's own checker on the result, and writes nothing unless the result passes.

   It ends by listing what is still yours to change:
   - the lines of your code, tests and README that name the old prefix;
   - the outside addresses in the manifest, which you replace with your own service's address (`https://acme-bins.ivendnext.app/...` on our hosting).

   Bin locations' service takes its prefix from a setting, `BLN_PREFIX`, so its code needs no change for the name.

4. **Give it the shape of the app you started from.** A library app is its sample with a few edits for our hosting, and the sample's README names them. For *Bin locations* (S2's README, *The till key alone, hosted by CitiXsys*), there are two:
   - **Its feed.** The feed is how **Connect again** hands your service the retailer's user:

     ```json
     "registered_applications": [{"name": "ACME BINS Bins feed",
       "description": "the Where is it? service reads the shop's bin records", "events": ["ACME BINS Item In Bin"]}]
     ```

   - **The till key's service only.** The sample also holds a second service (`service/app.py`, reached through the manifest's two `webhooks`), which takes what each sale sells out of its bin and runs as a service that stays up. Our *Bin locations* leaves it out. Take the two `webhooks`, and their address in `allowed_urls`, out of your manifest. Or keep them and host `service/app.py` as well.

5. **Make the change your customer needs.** For zones, three small changes:
   - in `manifest.json`, a **Zone** field on `ACME BINS Bin`:

     ```json
     {"fieldname": "zone", "fieldtype": "Data", "label": "Zone", "in_list_view": 1,
      "description": "Where in the store this bin is: Cold room, Cage, Shop floor."}
     ```

   - in `service/where.py`, `bin_rows` reads each bin's zone from the bin itself, so a bin's zone shows at once, on records old and new:

     ```python
     bins = sorted({r["bin"] for r in held if r.get("location") in kind_of})
     zone_of = {b["name"]: b.get("zone") for b in rows(f"{prefix} Bin", ["name", "zone"], [["name", "in", bins]])} if bins else {}
     return [{"item": r["item"], "bin": r["bin"], "qty": r["qty"], "kind": kind_of[r["location"]], "zone": zone_of.get(r["bin"])}
             for r in held if r.get("location") in kind_of]
     ```

   - in `core.py`, the answer names the zone after the bin, and a test pins it (`tests/test_zone.py`):

     ```python
     def _zone(row: dict) -> str:
         return f", {row['zone'].strip().lower()}" if (row.get("zone") or "").strip() else ""
     # … f"{code}: shop floor {floor[0]['bin']} ({_qty(floor[0]['qty'])}){_zone(floor[0])}{more}"
     ```

   Then set your own `title` (*ACME Bins*), `publisher` (your company), `version` (`1.0.0`) and `description` in the manifest.

6. **Check it, then try it on your sandbox.**

   ```bash
   python3 tools/check/check.py apps/acme_bins                    # the shop's checks, before anyone sees it
   python3 -m unittest discover -s apps/acme_bins/tests            # your tests
   BASE=https://<your sandbox> KEY=<key> SECRET=<secret> python3 tools/deploy/deploy.py apps/acme_bins/manifest.json             # shows what it will do
   BASE=https://<your sandbox> KEY=<key> SECRET=<secret> python3 tools/deploy/deploy.py apps/acme_bins/manifest.json --consent   # installs it
   ```

7. **Deliver it.**
   - **To one customer:** make a `library/` folder in your app for the App library ([Publish your app](../site/pages/publish.md), *What goes in your project*). Set `{"public": false}` in its `library.json`, and publish to that customer's own *Made for you* shelf. A shelf for one customer needs no approval by us:

     ```bash
     LIBRARY_DELIVERIES='[{"customer": "chain-a", "name": "Chain A", "sites": ["chain-a-test.ivendnext.com", "chain-a.ivendnext.com"]}]' \
     python3 tools/publish/publish.py publish apps/acme_bins --partner acme
     ```

     You send the customer its shelf key. Their administrator pastes it once under **App library → Open your shelf**, reads what your app will do, and installs it, first on their test site.
   - **To every retailer:** set `{"public": true}`, write its card and its guide, and publish the same way. Its first listing is reviewed once by us; your company is then its maker in the App library.

8. **Run its service.**
   - **On iVendNext App Hosting** (for one customer or for every retailer): run it once, as a function. Each retailer's site connects it by itself after the install, whether the retailer took it from the public list or from its *Made for you* shelf: each publish of your app to a shelf carries its own key for that customer's sites. Deploy it once:

     ```bash
     python3 tools/deploy_app/deploy_app.py apps/acme_bins --zip acme-bins.zip --root . --plan starter --partner acme
     ```

     It builds the package and prints the order we run. Your app answers at `https://acme-bins.ivendnext.app`, with `BLN_PREFIX=ACME BINS` and `IVN_LIBRARY_APP=acme_bins`. Each retailer's site connects itself after its install. Once the retailer chooses the app's user on the feed (step 4) and presses **Connect again** on your app's record, your service has that retailer's user. An app that only answers presses, listed on the App library's public list, carries no hosting charge.
   - **On your own server, for one customer:** set the retailer's three values (S2's `service/where.py` names them):
     - `IVN_POINT_SECRET`, the till key's secret, which the install shows once in Desk, on the till key's record;
     - `IVN_SHOP_URL`, the retailer's address;
     - `IVN_SHOP_KEY`, the API key of the app's user.

9. **If the customer already uses our app, move its records.** Install yours beside ours: the two prefixes never share a name. Then copy every record across:

   ```bash
   BASE=https://<the customer's site> KEY=<key> SECRET=<secret> python3 tools/deploy/copy_records.py ivendnext_bln acme_bins            # shows what it would copy
   BASE=https://<the customer's site> KEY=<key> SECRET=<secret> python3 tools/deploy/copy_records.py ivendnext_bln acme_bins --write    # copies
   ```

   It copies in the order the links need (locations, aisles, bins, then what is in each bin), with each record's table rows, and moves each item's default bin into your field, never over a value already set in yours. Bin locations names its records from their own fields (a bin by its code), so you can run it again at any time: it copies only what is new. Check the counts it prints, then uninstall our app from its package record. Its uninstall also keeps a copy of every record in a file.

10. **Keep it running.** Each version of what your app relies on (an extension point's contract, an API call, the manifest format) is served for 12 months after its successor ships, so your customer's upgrades keep your app running ([chapter 18](../guide/18_versioning_and_support.md)). Read the kit's changelog before each release of yours.

11. **Sell it again.** The next customer with zones gets *ACME Bins* on its own shelf. When it suits many retailers, list it once for every retailer (step 7).

## Good to know

- **A site can hold several companies' shelves.** Each opens with its own shelf key, and your app takes its updates only from your shelf.
- **Hosting with us** is ordered through your account manager, with the order `deploy_app.py` prints. Each new version is a new package you send us.
- **Taking our improvements.** Your copy changes only when you change it. At each kit release, `git fetch kit` and read what changed in the sample since you copied it (`git diff <the kit commit you copied> kit/main -- samples/s2_bins`); take what you want into your copy.
- **A copied app keeps the extension points it uses.** A copy of a till key app is a till key app: the doors, their limits and what the retailer consents to are the same as the original's (each sample's README says them).

## Technical notes

- **What `rename.py` changes:**
  - every string in the manifest that names the old prefix as a whole word, or the old app name at the start of a field;
  - a role named with the prefix's first word only (`PP Integration`);
  - the `app`, `handler` and `package` of an `app.json` beside it.

  It refuses a prefix whose first word iVendNext reads in field names (`FREE`, `PRICE`, `IS` …, listed on the save rules page), and a result iVendNext's checker or the install would refuse. It never edits your code: it lists it, line by line.
- **What `copy_records.py` reads and writes:**
  - It reads, from the site's own record of each install, the record types each app made and the fields each added to the retailer's records.
  - It matches each record type and field by its name after the prefix (`IVENDNEXT BLN Bin` → `ACME BINS Bin`).
  - A field the first app has and yours does not is named, never guessed. A cancelled record is not copied. It deletes nothing, on either side.
  - A record whose name comes from its own fields (a bin from its code) keeps its name, and a second run skips it. A record the site names itself (a number or a random name) gets a new name, and each link to it follows; such a record type is copied only into an empty one of yours.
  - The key is a System Manager's.
- **Tested:**
  - **Every sample:** each manifest in the kit's samples, renamed, passes iVendNext's checker with no old name left (`tools/manifest/tests/test_rename.py`).
  - **The worked example on a demo site:** *Bin locations* held 10 records and an item's default bin, and *ACME Bins* was installed beside it; *ACME Bins* in the form of step 4, its feed installed switched off, installs and uninstalls cleanly.
    - The copy moved every record, field for field, and the item's default bin. A second run copied nothing.
    - With zones set on two bins, the service answered as above.
    - After *Bin locations* was uninstalled, *ACME Bins* still held every record.
  - **The hosting package:** built for `acme-bins.ivendnext.app` and imported as the hosted function imports it, it answers `/health` and refuses an unsigned till call.
