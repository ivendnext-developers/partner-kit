# Your own card or mobile-money connector — the recipe

A **payment connector** lets a retailer take money through a payment provider we do not connect ourselves: a card terminal's cloud service, mobile money, or pay-later. You build it on your own server. The retailer's payments app calls it over HTTPS on the gateway contract **`paygw/1`**, revision 1.0, and nothing of yours runs inside the retailer's iVendNext.

**Reference implementation:** [`contracts/paygw/partner_stub.py`](../contracts/paygw/partner_stub.py), the payments team's own stand-in connector, copied unchanged. It is the connector their tests, their conformance kit and their walk on a real till ran against. Its "provider" is a toy ledger in memory, so it shows what your connector owes the retailer and leaves out the provider call that you write. **The contract:** [`contracts/pages/paygw.md`](../contracts/pages/paygw.md), the kit's copy of revision 1.0.

**When to use it.** The customer wants a card terminal or a mobile-money or pay-later provider that our own payment apps do not cover. If the retailer wants its own balance spent at the till (store credit, cash back), that is a wallet instead: [A partner wallet at the till](wallet.md). If one of our payment apps already covers the provider, use it (chapter 11).

## Pick your profile

A connector serves one way of paying. If you serve two, you publish two connectors.

| Profile | What the customer does | Rail in your declaration | How your connector answers *take this payment* |
|---|---|---|---|
| **Card** | taps or inserts a card at a terminal the provider runs from its cloud | `card_present` | approved or declined, while the cashier waits (up to 60 seconds) |
| **Push: mobile money** | approves the payment on their own phone | `mobile_money` | *pending* at once with your own handle; you tell iVendNext when it finishes |
| **Push: pay-later** | approves on their own phone, online | `card_not_present` | the same as mobile money |

The stand-in has one profile for each: `card_cloud`, `momo` and `bnpl` (its other two, `card_agent` and `wallet`, are a counter-wired terminal, which comes in a second phase, and a wallet, which has [its own recipe](wallet.md)).

## What iVendNext asks your connector

| iVendNext asks | You answer |
|---|---|
| **Take this payment** (authorise) | approved with the amount actually taken and your approval code, declined with a reason, or (push) pending with your own handle. The same reference asked twice is one charge, answered the same way. |
| **What happened to this reference?** (status) | the answer about exactly that payment. Never the answer about another one, and *never received* only when you never sent it to the provider. |
| **Give it all back** (reverse) | approved with the amount given back. Asking twice is safe and answers approved again. |

A card refund is still made on the provider's own machine and recorded at the till; on this contract only a wallet answers *refund*. When a push finishes, your connector calls iVendNext back; iVendNext also asks *status* on its own, so a lost callback slows the answer down but does not lose the payment.

## Steps

All of this is done on your own sandbox, on its screens, as the site's administrator. Ask CitiXsys to install the remote gateway payments app on your sandbox site (the one the wallet uses; a new sandbox site does not carry it) and to switch on its payments test mode, without which the sandbox refuses a sandbox certificate (step 3).

1. **Run the stand-in first.** `IVN_POINT_SECRET=<a secret you choose> python3 contracts/paygw/partner_stub.py --profile card_cloud --port 8443 --no-tls`, behind any public HTTPS address: iVendNext refuses plain http and private addresses. It listens on 127.0.0.1, which suits a tunnel on the same machine; on a small host add `--host 0.0.0.0` behind a proxy that terminates HTTPS. Use `--profile momo` for a push. It knows two merchant references, `M-STUB-1` and `M-STUB-2`; a card payment that carries none is still taken. Going through the steps below with it before you write a line tells you the retailer's side works.
2. **Write your connector.** Copy the stand-in's signed route and its answers. Keep what it gets right: it keys every lookup on (`site`, `reference`), puts `site` and `currency` in every answer, answers a repeated reference with its first answer, and refuses a body whose `verb` is not the route it came in on. ⚠ **One thing the stand-in cannot show you:** its ledger *is* its provider, so it has no provider call to lose. Yours has. **Store our reference in your own record before you call the provider**, and if the provider's reply is lost, answer that reference `unknown` for ever, ⛔ never *never received*: an absence for a payment the provider may have taken lets iVendNext cancel a real charge (the contract's §2).
3. **Sign your sandbox certificate** with [the sandbox certificate tool](../tools/sandbox_cert/README.md): your declaration, your partner name and the connector's name. Start from the stand-in's declaration for your profile (`DECLARATIONS` near the top of the file) and change its markets: they must include the two-letter country of each retailer company that will take the payment, or going live refuses (the sandbox's site is a US company). `can_prove_absence: true` is a promise that you can tell *never received* from *lost*: make it only if your provider can.
4. **Remote Connector → New.** Paste the certificate, your service's **bare address** (`https://<service>`: iVendNext adds `/paygw/1/<verb>` itself, so an address ending in `/paygw/1` doubles it and every call answers 404) and the secret: the same secret your connector checks signatures with (for the stand-in, its `IVN_POINT_SECRET`). Save. The form shows the **site id**.
5. **Give your connector** the secret and the site id, and restart it. Your connector binds the two and refuses another site's calls; the stand-in has no setting for this (it answers whatever site calls it), so with the stand-in this step is only the secret.
6. **Payment Account** (a display name, the company, provider: your connector, environment *test*, the retailer's currency, and the **Merchant reference at the partner**: the reference your connector knows this merchant by).
7. **Card only: Payment Device.** A label, the account, the till (POS Profile) it serves, transport *cloud*, and the **Terminal**: your name for the terminal, which reaches your connector as `device` on every *take this payment*. A push connector has no device.
8. **Payment Connection** (the company, the rail from your declaration, your connector, the account; *Certification required*: *not required* on a sandbox) → **Test connection.** It must pass: iVendNext asks your connector about a reference that never existed, with the merchant reference, so a merchant you do not hold fails it.
9. **Go live.** The payments app makes your connector's payment method and binds a card device's till. Put the payment method on each till's POS Profile; where that POS Profile links a payment template, add it there too.
10. **Push only: a contact for the customer.** A push declares `payer_required: true`, so the till refuses it for a customer with no mobile number or email on record, and nothing is taken (walked with a wallet that declares it; not yet with a push).

### When your connector does not answer

The till never charges twice on a guess. A card payment with no answer in time is held as *not sure*: the cashier is told not to charge the customer again, and iVendNext asks *status* until it knows. A payment that was taken but should not stand (the sale was cancelled, or you took more than was asked) is reversed by iVendNext, up to five times, and then a person is told. Make *reverse* safe to repeat and finish it within those tries.

## Certification and going live

On your sandbox, the **Run the conformance kit** button on the Payment Connection drives test payments through your connector and gives you a sealed report to download. Your sandbox copy must answer the kit's two test verbs, `induce` and `settle` (the stand-in does, unless started with `--live`); without them the report reads **INCOMPLETE**, which does not qualify. Your live connector refuses both with 403.

When the kit reads **CERTIFIED** and **SEALED**, send the downloaded report, unchanged, to `https://library.ivendnext.app/v1/payment-certificate` (POST). Paste the `certificate` you get back into the Remote Connector on the customer's site. No one at CitiXsys needs to act, and no pilot store is required. Your partner code is bound to the site you first certify from. The customer's site needs our remote gateway app at 2.1.0 or later.

## What is proven, and what is not

- **The card profile, walked on our test site** (2026-10-11) with the stand-in behind a public HTTPS address, through iVendNext's own screens and the till: a tampered certificate refused, the genuine one accepted, *Test connection* passed, a card payment approved and booked to the connector's own payment method, a lost answer held as *not sure*, a forged callback refused, the partner's signed callback settling it (the till's question then showed it approved; recovery by the retailer's question alone was not walked), a reversal answered approved, answered *unknown* (one try counted), not answered at all (no try counted), and a payment taken for more than was asked reversed for what was taken; then the day closed. In a second part of the walk, one till took a sale through our own card app and then one through the stand-in, on the same day.
- **Push and pay-later:** the stand-in's `momo` and `bnpl` profiles read **CERTIFIED** in the payments team's own kit tests (2026-10-11), over HTTPS through the real app. **Not walked at a till.**
- **The kit's copy of the stand-in:** run as a partner would (both `card_cloud` and `momo`), it answered signed calls as the contract says: one charge per reference asked twice, *status* without a merchant, *never received* for a reference it never had, reverse twice, a body signed for one verb refused on another, a bad signature refused, and the test verbs refused by `--live`.
- **A connector of anyone else's** has not yet been certified.

## Technical notes

- **The wire.** Every call is a signed POST to `https://<connector>/paygw/1/<verb>`, the till key's scheme: `X-iVendNext-Signature` is base64 HMAC-SHA256 of `<timestamp>.<raw body>` with your secret, `X-iVendNext-Timestamp` within 5 minutes of your clock. Every body carries `v`, `site` and `verb`. Money is in the currency's minor units with `currency` and `currency_exponent`, and every money answer echoes `currency`. Full text: [`contracts/pages/paygw.md`](../contracts/pages/paygw.md) §1–§4.
- **The three things to get right first** (a `User-Agent` naming your connector on every call you make to us, callbacks signed as our calls are, reverse safe to repeat): the payments team's starter note, copied in [the wallet recipe](wallet.md#the-partner-starter-note); it applies to every connector.
- **The callback.** `POST https://<shop>/api/method/ivendnext_pay_remote.api.callback?connector=<provider key>` with `{v, site, connector, reference, answer}`, signed. Retry only while iVendNext answers `in_flight` or `indeterminate`; stop on `acknowledge: true`. The stand-in does not send callbacks (the walk sent its callbacks from a small script beside it); the contract's §6 has the rules.
- **The flaws.** The stand-in can be started with `--flaw <name>`: each one is a way a connector goes wrong (charges twice, answers about another payment, reverses the wrong amount), kept so the payments team can prove the kit refuses it. Never start a connector you use with one.
- **One stale line in the contract.** Its §4 says chapter 11 of this kit lists six operations; chapter 11 now names the contract's four verbs. The contract's own verbs (§3) are the rule. We have told the payments team. The stand-in's opening comment also carries a few of the payments team's own working names (a design note's id, two work names); they name nothing you need.
- **Where these files come from:** [EXPORT_SOURCES.md](../EXPORT_SOURCES.md). A defect in either copy is a defect in the payments app's file: report it on the [feedback forms](../feedback/README.md).
