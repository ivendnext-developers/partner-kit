# Making the integration user for a connected app — the recipe

A connected app signs in to a retailer's iVendNext **from outside**, with an API key: a warranty service, a bin-location service, a marketplace bridge. This recipe shows how iVendNext gives that app its own user, holding only the rights it needs. It is for iVendNext Partners, and for the CitiXsys Consulting Team. **Reference implementation:** the integration user the two sample services use (`samples/s1_warranty/service/`, `samples/s2_bins/service/`).

**When to use it.** Rung 2 of the build ladder: a connected app. Try configuration first (pricing rules, promotions, print formats, sale details, permissions). If the job really needs your own server, every connected app gets **its own** user, made this way. A till key hosted inside the retailer's iVendNext, an embedded app and a manifest do not need one: they run as the cashier, the person booking the sale, or nothing at all.

**The rule in one line.** One connected app = one desk user = one user licence, holding one narrow role. The retailer decides which apps get a user, what each may do, and when to switch one off.

## Steps

The retailer's administrator does these in iVendNext Desk.

1. **Give a role for this app alone the rights it needs** (Desk → Role Permissions Manager; Desk → Role → New only if no role of that name exists). If your manifest names the role in its permission rows and the role starts with your prefix, the install makes it (on a site whose POS app is at `e149dce4` or later; any other missing role is refused, so iVendNext makes it first) and a manifest can grant it rights only on **your own** record types: the rights on the retailer's own record types are the ones you add here, and a card's setup steps say so. Give it only what the app reads and writes. The bin-location sample's role, for example:

   | Record type | Rights |
   |---|---|
   | Item, Customer, Warehouse, Sales Invoice, POS Invoice, Bin (stock balances), POS Profile | read |
   | Comment | read, create |
   | Stock Entry | read, write, create, submit |
   | Serial No; Serial and Batch Bundle | read, write, create (+ submit on the bundle) — only if the app books **serialised** stock |
   | the app's own record types (from its manifest) | read, write, create — granted by the manifest itself |

   Do not start from an existing role such as Stock User: it carries far more than your app needs.

   **Reading a record also needs read on the records it links to.** A key that reads a Purchase Receipt but holds nothing on Supplier was answered `403 … does not have doctype access … for document Supplier` (measured on a test site): the receipt names its supplier. So when a read answers 403 for a linked record type, give the role read on that type and write the reason beside the right; check this for each record type your service follows.

2. **Make one user for the app** (Desk → User → New):
   - an e-mail that names the app, e.g. `bins-service@yourshop.example`;
   - tick **Is Desk User**. iVendNext refuses a user that is neither a desk user nor a POS user, so there is no API-only kind;
   - give it only the role from step 1;
   - set no password. The user never signs in to Desk: only its API key is used.

3. **Generate its API key and secret** (User → Settings → API Access → **Generate Keys**). The secret is shown **once**. Put it straight into your service's secret store. Every request then carries:

   ```
   Authorization: token <api key>:<api secret>
   ```

4. **Know what the key can do.** On a product before 2026-09-30, every desk user, the app's user included, also held iVendNext's **Workspace Manager** role. That role lets a user change the shared Desk workspaces. With it, the key could put content on a shared workspace that runs in the browser of whoever opens it, an administrator included. So **on such a product a connected app's key can do what an administrator can.** Since 2026-09-30 only a System Manager gets that role, so an app's user holding only the role from step 1 does not have it; the manifest installer refuses an integration user given it (`guide/07_manifests.md`). What the key can do is the retailer's choice when it connects the app. Keep the key in a secret store, never in code or chat, and rotate it at any doubt (step 6).

5. **Prove the key, and prove its limits:**

   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: token $KEY:$SECRET" \
     "$BASE/api/resource/Item?limit_page_length=1"          # 200
   curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: token $KEY:$SECRET" \
     "$BASE/api/resource/Journal%20Entry?limit_page_length=1" # 403: outside the role
   curl -s -o /dev/null -w '%{http_code}\n' "$BASE/api/resource/Item?limit_page_length=1"  # 403: no key
   ```

   The request collection checks the same two refusals (files `17_refused_outside_role` and `18_refused_without_key`). Run it with curl and jq only: `BASE=… KEY=… SECRET=… bash api/collection/run.sh`.

6. **Rotate or revoke the key.** To rotate it (a person who saw it leaves, or on a schedule), press **Generate Keys** again. The old secret is refused (`401`) at once, and the new one works (`200`). Update your service's secret store in the same change. To switch the app off, the retailer **deletes the user**, or generates new keys and keeps the secret to itself. Disabling the user is not enough: its key still signs in.
   ⚠ **A user that has taken a workflow step cannot be deleted.** iVendNext keeps a record of every step taken (a *Workflow Action*), naming the user and the role that took it; a completed one is visible to the site's Administrator alone, so no partner key can find and clear them, and iVendNext answers *"linked with Workflow Action"*. For such a user, switch the app off by disabling the user, generating new keys that no one keeps, and disabling the role. A later setup run switches them back on. The site's Administrator can delete them if the retailer wants them gone.

## What is refused, and why

- **An API-only user.** A user must be a desk user or a POS user, so a connected app takes a desk user and its licence. That is deliberate: the licence is how a connected app is counted.
- **A server-to-server sign-in with enforced scopes.** Not available today. The API key plus a narrow role is the boundary, so keep the role narrow.

## When your service is down, and when the till is offline

The user does not change either. If the key is revoked or rotated without your service knowing, every call answers `401`. Alert on it, and do not retry it in a loop. Till sales made offline reach you when the till syncs, through your webhooks (`recipes/webhook_receiver.md`).

## What we would like to improve

- A server-to-server sign-in whose scopes are enforced against record types.
- Stop every desk user, integration users included, from listing every user on the site.

## Technical notes

### Making the user from a script

Over the record API (`POST /api/resource/User`), step 2's *Is Desk User* tick is the field `custom_is_desk_user`: set it to `1` on the new user. Without it iVendNext refuses the user: *"Select at least one option: 'Is Desk User' or 'Is POS User'."* (Sample S22's `apply_config.py` does this.)

### What was proven where

- The reference integration user is our test bench's, which the two sample services use (`samples/s1_warranty/service/`, `samples/s2_bins/service/`), proven on the bench.
- On our test bench the steps were made by a setup script that writes the same records, and each result was then measured against the live record API.
- Workspace Manager since 2026-09-30: engine commit `d52056c` gives it to a desk user only as a System Manager (`ivendnext_pos/doc_events/user.py`, read at the bench's engine pin `f7afcfb61`); the manifest installer refuses an integration user given it, `guide/07_manifests.md` (the older engine simulated). Measured on the bench at its earlier pin (`ivendnext_pos` `457ba607d`, without that commit; 2026-10-03): with the role, the key could put content on a shared workspace that runs in the browser of whoever opens it, an administrator included. Not measured: whether a key without that role can reach an administrator's browser another way.
- Key rotation, **measured on the bench:** the old secret is refused (`401`) at once, and the new one works (`200`).
- Disabling the user is not enough: its key still signs in (measured on our test bench, 2026-10-07).

### Tests

- `api/collection/run.sh` (curl and jq only) signs in with the key and checks both refusals: `BASE=… KEY=… SECRET=… bash api/collection/run.sh`.
- The measurements above — what the Workspace Manager role allows, and key rotation — were taken on our test bench.
