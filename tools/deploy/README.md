# deploy — put your manifest on your own sandbox

One command installs, updates or removes your manifest on a site you administer, through the same methods as the
shop's **Retail Extension Package** screen. Nobody from our team takes part.

1. **Make an API key** for your sandbox's administrator (Desk → your user → API Access → Generate Keys).
   If **Generate Keys** answers *"Select at least one option: 'Is Desk User' or 'Is POS User'"*, tick **Is Desk User** on that user first (the field `custom_is_desk_user`), save, then generate. The built-in **Administrator** of a site you made on your own bench has neither tick.
2. **See what it would do.** Nothing is installed:

   ```bash
   BASE=https://<your-sandbox> KEY=<api key> SECRET=<api secret> python3 tools/deploy/deploy.py manifest.json
   ```

   It checks the manifest on your machine first (`tools/manifest/validate.py`) and stops on a refusal. Then the site
   checks it again and prints its own summary: what it makes, every outside address, what runs from the moment of
   install. For a higher version it also prints what changes from the installed one.
3. **Install it:** add `--consent`. It checks again, prints the summary the site returns then, and installs with that one. It waits for the install and prints the result, each
   secret your manifest's webhooks or services were given (shown once here; each stays readable on its own record),
   and what the shop still has to switch on.
4. **Remove it:** `deploy.py uninstall "<app> <version>"` writes an export of your records first and prints where.
   **If a job failed or was cut off:** `deploy.py finish "<app> <version>"` completes it or takes it back.

Exit code: 0 done (or checked, without `--consent`) · 1 refused or failed · 2 usage · 3 still running after `--wait`
seconds (default 900). Python 3 standard library only.

## Technical notes

- **Consent.** `--consent` sends back the summary's SHA-256 that the site returned in the same run, never a value you
  type. The site refuses a consent whose summary no longer matches the manifest.
- **The site needs the install screen:** the POS app from commit `87812e14`. On a site without it, `deploy`
  stops at the check with *the site answered HTTP 417 to /api/method/ivendnext_mpos.api.extension_package.check: … Failed
  to get method …*. A manifest that carries label layouts or field rules on the receipt needs that app from commit
  `7be4333b` (2026-10-10) or later: an older install screen refuses them, although the kit's checker passes them. A label layout that uses `{weight}` or `{unit_price}` needs `88512583` (2026-10-11) or later.
- **Tests:** `python3 -m unittest discover -s tools/deploy/tests` — the whole tool over HTTP against a local stand-in
  site: no install request without `--consent`, the fingerprint echoed exactly, a refusal (yours or the site's) stops
  the run, the wait ends on every final status.
- **Proven on our test bench (2026-10-10):** check without consent, install, update to a higher version, export and
  uninstall, a refused finish, and a manifest with webhooks and a till key whose secrets were printed.
