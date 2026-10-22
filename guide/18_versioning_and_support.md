# 18. Versioning — how long a version keeps working

This chapter says what counts as a breaking change, how a version is announced, and how long an old version is served. It is for a builder deciding whether to build on an extension point today, and for a licensed customer's IT team deciding when to move to a new one.

**Reference implementation:** [the kit's changelog](../CHANGELOG.md), where a change is announced · the version line at the top of each extension point's library page · `manifest_version` in [a manifest](07_manifests.md).

## When to use it

Before you build on an extension point, on an API call the kit describes or on the manifest format; and each time we announce a change.

## The policy

- **The general release is iVendNext POS 2.0.0.652, of 18 October 2026.**
- **From the general release, each version is served for 12 months after its successor ships.** That holds for a version of an extension point's contract, of an API call the kit describes, and of the manifest format.

**The general release** is iVendNext POS 2.0.0.652, released on 18 October 2026 and announced in the kit's changelog. Every POS build is numbered `2.MINOR.PATCH.BUILD`, and a build keeps its number when it is released.

## What counts as breaking

A change is breaking when something that worked against a version stops working, or answers differently, without you changing anything. For each of the three:

| | Breaking | Not breaking |
|---|---|---|
| **An extension point's contract** | removing or renaming a field you are sent, or an answer you may give; changing what a field means or its units (money is a whole number of the currency's smallest units, quantities are in thousandths); making an answer you may give stricter (a shorter limit, a shorter time to answer, a refusal of something that was accepted); changing what the till does with an answer, or when your service is down or the till is offline; changing how a call is signed | what the library says is added within a version: a new label on the event feed, a new kind of save rule, a new screen or field in a field rule's list. An existing one never changes what it does |
| **An API call the kit describes** | a call that stops answering as described: a path, a field, a status or a meaning changes | a description that gains a call |
| **The manifest format** | a manifest that installed before, and now does not, or installs something different | a new kind of record a manifest may carry |

A change that would break a version-1 service is a new version, published beside the old one; the library says so for the remote till key and for the capture.

*An example:* manifest version 2 reads every version-1 manifest, but only once each of its permission rows writes all nine rights (chapter 7).

## How a version is announced

- **`manifest_version`** in your manifest. The checker reads versions 1 and 2; write 2 (chapter 7).
- **The version line of the contract's page.** Every extension point's library page says *Version 1*.
- **A header on the call.** A call to your service for a Desk action, a check, a capture or a fulfil at sale (POS build 2.0.0.654 on) carries `X-iVendNext-Point: <point>/<version>` — for example `check/1`, `capture/1`, `desk_action/1`, `fulfil/1`. The body repeats it where the page says so (`"point": "check/1"`, and a `"v": 1` in the context). The remote till key's call carries `User-Agent: iVendNext-POS-AppKey/1` instead. A payment connector's calls (card, push or wallet) carry `X-iVendNext-Point: paygw/1` (the payments core's wire contract). Pricing sends your server no call: the certified module runs inside the shop. A partner page is framed by the till, which sends your server no call: its version is the `"v": 1` in the signed context. The event feed, the save rules, the scan source, the field rules, the fiscal reader, the label layout, the receipt settings and the list marks send no call to you either: the shop declares them, and their page's version line is the version.
- **The changelog**, a dated entry for every change.

## Steps

1. **Read the version line** of each page you build on, and write the version into your service's tests and logs.
2. **Read the header** on each call and answer the version you were built for. A call that names a version you do not know is not one to answer in the old way.
3. **Read the kit's changelog** before each build and before each release of your own.
4. **When a successor ships,** the version you built on is served for another 12 months: move to the successor inside that time.

## What is refused, and why

- **A promise beyond the policy.** We give no period for a version after the 12 months.
- **A promise about anything but the three.** The samples, the recipes and the tools are examples, and change with the kit.

## When your service is down, and when the till is offline

A version does not change these answers: what the till does when your service is down, and when it is offline, is part of each extension point's contract (chapter 9), so a change to it is a breaking change.

## Numbering your own app — our recommendation

This is a recommendation, not a rule: we do not check your numbers. We number every app we build this way, and a customer's IT team reading their site sees the same shape across apps.

- **Four numbers: `MAJOR.MINOR.PATCH.BUILD`**, for example `2.1.0.57`.
- **MAJOR is the iVendNext engine's major, `2` today**, for an app that works with iVendNext. On our builds the site's *About* screen shows the engine's major as every app's first number, so your app's number has the same shape as ours.
- **MINOR and PATCH are yours:** raise MINOR for a release that adds something, PATCH for a release that only fixes.
- **BUILD is set by a script, never typed:** the count of commits on your main branch's first-parent line, counted on your main branch at the commit you ship. Every build then has its own number, a bigger number is always newer, and the number leads back to one commit.
- **No `-beta` or `-rc` in the number.** A build you give a test shop and the same build you give everyone keep the same number.
- **Never ship `0.0.1`** (every new app starts there) or a number you have shipped before: two different builds would then show the same number.
- **Your manifest's `version`** (chapter 7) can follow the same form. It is your pack's version; `manifest_version` is ours.

## Technical notes

### Numbering your own app: the code

In your app's package `__init__.py` (the folder that holds `hooks.py`):

```python
try:
    from ._build import BUILD
except ImportError:
    BUILD = 0

__version__ = f"2.1.0.{BUILD}"
```

Add `_build.py` to `.gitignore`. When you build or deploy, write it from your app's repository root, in a clone with full history (a shallow clone counts wrong), with your main branch's commit checked out:

```bash
printf 'BUILD = %s\n' "$(git rev-list --count --first-parent HEAD)" > <your_app>/_build.py
```

Without `_build.py` the app reports `2.1.0.0`: a build nobody stamped, which is what a developer's own machine shows. A package built from the app (`pip install`) reads the same number.


### What the kit has proven

- **The header is in the product's shared caller.** At the POS app's commit `b3bd26557` (2026-10-08), the caller that serves the Desk action, the check and the capture (`business_logic/partner_point.py`, `POINT_HEADER`; called from `desk_action.py`, `partner_check.py` and `partner_capture.py`) sends `X-iVendNext-Point: <name>/<version>`, read from the extension point's own declaration. At T12's merge (`7d47d331a`, build 2.0.0.654) the fulfil at sale's calls go through the same caller (`partner_fulfil.py` → `partner_point.call`), so they carry it too. The library pages of the Desk action, the check and the capture state the header. The page does not use that caller: its page says only that the context carries `"v": 1`.
- **Every library page at that commit says Version 1.** The remote till key's page gives the `User-Agent` form; the event feed's, the save rules' and the field rules' pages say a new label, kind or screen is added within version 1.
- **The manifest checker accepts `manifest_version` 1 and 2** (`tools/manifest/validate.py`, `VERSIONS`).

### What it has not

- **No contract has had a successor yet,** so the 12 months has never been exercised, and no changelog entry has announced a change to a contract.
- **The list of what counts as breaking is ours, written from the library's own sentences and the one example above.** It is not exhaustive.
- **The header** is read from the code and the library pages, not from a recorded call.

### Sources

- **The policy** is our decision of 2026-10-08.
- **The library pages** read: all fourteen: `remote_till_key`, `event_feed`, `save_rules`, `desk_action`, `partner_page`, `fiscal_reader`, `partner_check`, `scan_source`, `partner_capture`, `fields`, `label_layout`, `receipt`, `price`, `wallet` (`docs/extending/` in the POS app, at `8ce9bed2`).

## See also

[1. Welcome](01_welcome.md) · [3. The ladder and the four rules](03_ladder_and_never_list.md) · [7. Manifests](07_manifests.md) · [9. The extension points](09_points_and_requests.md) · [14a. Deploying to a chain](14a_deploying_to_a_chain.md)
