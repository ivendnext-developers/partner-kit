<!-- Source: ivendnext/iVendNext_Payments docs/contract/PAYGW_1_REMOTE_GATEWAY_CONTRACT.md @ 36385b31a5d0, copied unchanged except the links: the documents it links to stay in the payments app's repository, which is not public, so they are named, not linked. Its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the payments board. -->
# The iVendNext Remote Gateway Contract — `paygw/1` (Payment Gateway Interface 1)

**Revision:** 1.0 · **Status:** APPROVED, 2026-10-13 · **Checked against:** the code on `development`
at `ee9e616` (`apps/ivendnext_pay_remote` and `apps/ivendnext_payments_core`).

**Two interfaces, two documents.** This document is **Payment Gateway Interface 1** — the wire a
partner's own server speaks. Inside the customer's site, our app `ivendnext_pay_remote` turns that
wire into an ordinary gateway under **Payment Adapter Interface 1**, whose document is
`PAYMENT_ADAPTER_CONTRACT_v0.3.md` ("v0.3" is a revision of
interface 1). A partner implements **this** document; it never implements the adapter contract
itself. Read alongside: `CONFORMANCE_KIT.md`,
`BUILD_A_GATEWAY.md` §2b (connectors are signed data, not classes) and
`apps/ivendnext_pay_remote/README.md`.

⚠ The adapter contract's description of `refund` predates the wallet profile. For the wallet
profile (§3a), this document and the code are the authority.

---

## 0. What this is, in one paragraph

A partner builds a **payment connector** on its own server. It speaks this wire format over HTTPS.
Inside the customer's site, **our** gateway app `ivendnext_pay_remote` is an ordinary adapter under
the adapter contract, and its "provider" is the partner's connector. So the core's one durable
record, its recovery ladder, its sweeps and its sale-key guard serve the partner exactly as they
serve our own gateway apps. ⛔ **Nothing of the partner's runs in the tenant, and nothing the partner
sends ever writes our record.** The partner owns one provider's wire format and its own map from our
reference to the provider's handle. We own everything else.

```
till ──► payments core ──► ivendnext_pay_remote (ours, in the tenant) ══ paygw/1 over HTTPS ══► partner connector ──► provider
                ▲                                    │
                └──── resolve() ◄── signed callback ─┘  (the partner calls OUR app's route; the core's own receiver stays closed)
```

## 1. Transport

| Rule | Detail |
|---|---|
| **HTTPS only**, certificate checked against the host name | Plain http is refused when the connector is registered. A private-network address is refused (Partner Kit chapter 14b), and so are carrier-grade NAT and the IPv6 prefixes that embed an IPv4 address (NAT64 `64:ff9b::/96`, `64:ff9b:1::/48`, 6to4 `2002::/16`, Teredo `2001::/32`). These are refused unless a **test bench** allows them: the site's own non-production flag AND the bench's `common_site_config.json` key `paygw_test_bench` (which a tenant cannot write), plus `paygw_allow_private_addresses` for a private or loopback address and `paygw_ca_bundle` for a private certificate authority. Plain http is never allowed |
| **Every call is a signed POST** to `https://<connector>/paygw/1/<verb>` | Headers: `X-iVendNext-Timestamp`, `X-iVendNext-Signature` = base64(HMAC-SHA256(secret, `"<timestamp>.<raw body>"`)), `X-iVendNext-Request-Id`, `X-iVendNext-Point: paygw/1`. A timestamp more than 5 minutes from the connector's clock is refused. The **same scheme as the Partner Kit's till keys** (chapter 6), so a partner's existing verifier works unchanged |
| **Bodies** | JSON, at most 64 KB each way. ⛔ No redirect is ever followed. ⛔ No retry by the caller: the core's recovery ladder decides what happens next. Every body carries `v`, `site` and **`verb`**, inside the signed bytes. ⛔ **A connector refuses a body whose `verb` is not the route it arrived on** — so a signed `authorise` cannot be replayed at `/reverse`. Each verb's deadline (§3) is **in total** — resolution, connection, headers and body together, not per socket read. A partner that drips its answer is a missing answer |
| **Secrets** | One signing secret per connector per site, `Password`-typed (write-only), held on the tenant's **Remote Connector** record beside the certificate — ⛔ not in the core's account credentials. The reason: our app's `reverse` does not declare the adapter contract's optional `account` parameter (adapter contract §11.2), so a per-account secret could not be found on the one verb that must always work. ⚠ **One secret, no two-secret window yet:** rotate with the partner in one step; during a mismatch our calls are answered 401, and a reversal answered 401 costs one of five attempts (§4) |
| **Site id** | Minted by our app when the connector record is first saved, shown on the record, **set once**. The tenant gives it to the partner with the secret; the partner binds the two and scopes every map and idempotency lookup by it |
| **Site** | Every call carries `site`, an opaque id bound to that site's signing secret. ⭐ One connector serves many tenants, and our reference is unique per tenant only, so **the connector scopes every map and idempotency lookup by (`site`, `reference`)** — otherwise tenant A's approval answers tenant B's `authorise` |
| **Health** | `GET /health` → 200, unsigned, says nothing about any shop |
| **Reach** | The tenant calls out. ⛔ It never calls a private address, and our app **pins the address it resolved** for the life of the call (no DNS rebinding between the check and the connect). A connector with no public address dials **out** to a relay instead (§8) |

## 2. Money and identity on the wire

- **Money in minor units**, with `currency` (ISO 4217) and `currency_exponent` on every money call.
  Our app converts to the major units the core reads **using the transaction's own currency**,
  ⛔ never the answer's. Every money answer **echoes `currency`**, and an answer whose currency
  differs from the one asked is refused whole.
- **`reference`** is **ours** (`MPOS-REF-` + 12 hex characters). ⭐ **The connector answers on OUR
  reference.** It stores the map from our reference to the provider's handle **before** it calls the
  provider, so even a provider that cannot index our namespace (adapter contract §2.2, path (b)) is
  path (a) at this boundary.
  - ⛔⛔ **But a map row with no provider handle can never be called absent.** If the connector wrote
    the row, called the provider and lost the acknowledgement, it does not know whether the provider
    has the payment. For that reference it answers **`unknown` for ever, ⛔ never `exists: false`**,
    however its declaration reads. `can_prove_absence` covers only references the connector **never
    sent** to the provider.
- **`correlation_id`** is the connector's own handle. It is **required on `pending`** and returned
  whenever one exists. It is written once: a later answer carrying a different one is treated as an
  answer about another payment.
- **`merchant`** is the connector's own reference for the merchant, resolved by our app from the
  account the core names. ⛔ An account our app does not hold is refused **before any call**. An
  absent account falls back only to the site's **sole** account for that connector, and otherwise is
  refused (adapter contract §11.3).
- ⛔ **No card number, ever, and no free-form provider body.** The answer carries only the closed
  fields below. `instrument` is limited to `brand`, `last4` and `expiry` (`YYYY-MM`), as strings.

## 3. The verbs

Every body also carries `v`, `site` and `verb` (§1).

| Verb | We send | The connector answers | Deadline |
|---|---|---|---|
| `declaration` | `{v, site}` | §5 | 10 s. Not called by our app. The production certificate is issued from the certificate payload the sealed kit report names (§5, §9); a tenant runs that signed copy |
| `authorise` | `{v, site, reference, merchant, amount_minor, currency, currency_exponent, rail, device, payer{phone,email,name,party} (may be empty), payer_code?}` | an **Answer** (§4) | **60 s.** A card tap waits on a person. An asynchronous rail answers `pending` within 10 s (a partner obligation our app does not enforce — §10) |
| `status` | `{v, site, reference, correlation_id?, merchant?}` | an **Answer** about **that** reference (§4); about a refund reference, a **Refund Answer** (§3a) | 15 s |
| `reverse` | `{v, site, reference, auth_ref?, amount_minor, currency, currency_exponent}` — the WHOLE authorisation, addressed by **our reference**. ⛔ No `merchant` (§10). `auth_ref` is absent when the core is reversing a push it never heard back about (the sweep's aged `Pending`/`Timeout` rows) | a **Reverse Answer** (§4) | 15 s |
| `refund` *(wallet)* | `{v, site, reference, original_reference, auth_ref, merchant, amount_minor, currency, currency_exponent}` — `reference` is the refund's own | a **Refund Answer** (§3a) | 15 s |
| `preview` *(wallet)* | `{v, site, customer, merchant, amount_due_minor, currency, currency_exponent, store, sale_ref, lang}` | a **Preview Answer** (§3a) | **3 s**, the till's answer budget |
| `induce` · `settle` *(sandbox only)* | `{v, site, condition}` · `{v, site, reference}` | `{v, accepted}` · `{v, reference, state}` | 10 s. ⛔ **A live connector answers 403** |

**`status` and the merchant.** `merchant` travels on `status` ONLY on the core's connection test
(its reference starts `PROBE-`) — a payment that never happened, where it proves the credentials.
⛔ For a real payment, and for the conformance kit's own references, it is never sent, so the kit
certifies the request recovery really sends, and a merchant reference edited while a payment is in
flight cannot reach the question. Therefore:

- ⛔ **A connector must answer a status that carries no merchant.**
- ⛔ A connector answers `unknown` with reason `config_invalid` for a merchant it does not hold, so a
  wrong merchant reference cannot pass the connection test.
- ⛔⛔ **The merchant only shows WHO is asking; it never narrows the question.** The connector answers
  by (`site`, `reference`) and **never claims absence for a reference it holds under any merchant**
  (an operator may edit a merchant reference while a payment is in flight; an absence there would
  void a live capture).

## 3a. The wallet profile

A connector on the `wallet` rail is a partner's stored-value wallet (loyalty money, a closed-loop
card). It is additive: a connector on any other rail is unchanged.

1. **What a wallet declares.** `capabilities: ["balance_preview", "refund", "reverse"]` and
   `supports_refund: true` — all three together: the till refuses a wallet payment it has no preview
   for, and refuses a return it cannot pay back to the wallet. ⚠ A wallet certificate signed before
   the wallet profile (`["reverse"]`, `supports_refund: false`) still **loads**, as a reverse-only
   wallet, so a connector holding live payments is never deregistered; a till cannot use it (no
   preview, no refund) until it is re-certified with all three. Every other rail declares exactly
   `["reverse"]`, `supports_refund: false`.
2. **`preview`.** We send the body in §3 (`merchant` included: one connector serves many merchants).
   The **Preview Answer** is `{v, site, eligible, currency, balance_minor?, max_redeemable_minor?,
   label?, otp_required?, reason?}`, graded whole: `site` ours, `currency` the one asked; eligible ⇒
   `0 ≤ max_redeemable_minor ≤ balance_minor` and `label` 1–40 characters; not eligible ⇒ `reason`
   1–140 characters. **3 seconds, in total.** ⛔ A preview moves no money and writes nothing on our
   side. A preview that times out, is refused or is malformed dims the wallet at the till for that
   sale; it never raises at the till.
3. **`authorise` on a wallet** carries the customer as `payer.party` and, when the wallet asked for
   one, the customer's one-time code as the top-level **`payer_code`** — ⛔ never inside `payer`,
   never stored, never logged. A wrong code is `declined` with reason **`invalid_code`**, one of the
   core's standard reasons.
4. **`refund`.** We send the body in §3. The **Refund Answer** is `{v, site, reference, outcome,
   amount_minor?, currency?, correlation_id?, reason?}` — ⛔ `correlation_id` (your refund id) is
   **required on `approved`**; an approved refund without one is refused whole (`unknown`) and never
   settles. `reference` is the **refund's own** reference, minted by us (`MPOS-RFD-` + 12 hex
   characters); `original_reference` and `auth_ref` name the payment it gives back to — ⛔ only to
   that payment's wallet. Rules:
   - ⭐ **Refunding twice with one (`site`, `reference`) is ONE refund**: the second call returns the
     first answer and the same `correlation_id`. Kit scenario 19.
   - `approved` carries the `amount_minor` you actually gave back, which must be **exactly** the
     amount asked. A different amount is NOT refused at the wire: we record what you gave back, the
     refund stays unsettled, and a person is told at once — the return cannot book until it is
     corrected. A refund is never more than the payment has left; refuse with `declined` otherwise.
   - ⭐ **Correcting a wrong amount is yours.** Because one refund reference is one refund, our record
     of it follows your answer about that reference: correct your own record so that `status` about
     the reference answers `approved` with the amount asked (you gave back the rest) or `declined`
     (you gave it all back — then we let the return ask again). Until then the refund stays
     unsettled, we re-ask every five minutes, and the till refuses further returns of that sale.
   - ⭐ **A payment may be refunded in several parts**, each under its own refund reference and its
     own amount. Key your idempotency on the REFUND reference, ⛔ never on the original payment: a
     second part answered with the first part's refund is a refund answering for another refund.
   - The answer is about **the refund asked** — `reference` echoed. Kit scenario 20.
   - Deadline **15 s**. No answer is `unknown` on our side, and ⛔ **we never send the refund again**:
     we ask `status` about the refund's reference.
5. **`status` about a refund reference** answers the **Refund Answer** shape (no `auth_ref`):
   `approved` with the amount given back and the **same** refund id, `declined`, `pending`, or
   `unknown` — with `exists: false` only where the declaration attests `can_prove_absence` and the
   refund was never received (we then let the return ask again, so ⛔ an absence for a refund you DID
   make refunds the customer twice). ⭐ The question carries `correlation_id` (your refund id) when you
   gave one; ⛔ look the refund up by (`site`, `reference`) whatever it carries — never among payments
   only. An answer naming a different refund id is treated as being about another refund and settles
   nothing. A money answer echoes `currency`; an absence need not.
6. **The refund is the core's record**, not the payment's: a `Payment Refund` row, Pending and
   committed before we ask you, idempotent by the return's key, settled by `status`, and told to a
   person if it stays unresolved after five checks or if a confirmed refund is not named by any
   booked return within 15 minutes. A person who has checked with you may settle an unresolved refund
   by hand (never one you answered with a different amount, and never while its call may be in
   flight). ⚠ Once a booked return names a refund the core marks it booked for good; a return
   cancelled afterwards does not bring the alert back (a stated bound).

## 4. Answers — refuse-whole, per verb

**An Answer** (`authorise`, `status`): `{v, site, reference, outcome, amount_minor?, currency,
auth_ref?, correlation_id?, capture_state?, reason?, exists?, instrument?}`

- `site` is required on every answer, and an answer whose `site` is not ours is refused whole.
- `reference` **must equal the reference asked**, or the whole answer is refused (adapter contract
  §2.2).
- ⭐ **`authorise` twice with one (`site`, `reference`) is ONE charge**: the second call returns the
  first answer, the same `auth_ref` and the same `correlation_id` (adapter contract §2.3; conformance
  scenario 5 refuses a new handle). The core mints a fresh reference per push and its own guard is the
  sale key, so this is exercised by the provider's retries and the kit, not by us.
- `outcome` ∈ `approved · declined · pending · unknown`, and ⛔ `pending` ≠ `unknown`.
- `approved` ⇒ `amount_minor` (what was **actually** taken — the core reverses a mismatch
  automatically) **and** `auth_ref` (the address of every reversal). ⛔ Never card-shaped digits in
  `auth_ref`.
- `pending` ⇒ `correlation_id`.
- `declined` ⇒ `reason` from the standard set (`declined_by_issuer · insufficient_funds ·
  payer_cancelled · payer_timeout · device_unreachable · device_busy · config_invalid ·
  network_timeout · gateway_error`, plus `invalid_code` on the wallet profile).
- `exists: false` (with `unknown`) means **"the provider told me this reference is not there"**. It
  is honoured **only** where the connector's certified declaration attests `can_prove_absence` for
  that rail. A call the connector could not complete is `unknown`, ⛔ never an absence (adapter
  contract §2.4).
- `capture_state` is `captured`. ⛔ **`authorized_pending_capture` is refused on `paygw/1`**: no verb
  captures it later and the core does not read the state, so it would expire unpaid while the sale
  is booked. The connector captures **before** it answers `approved`.
- ⚠ Partner Kit chapter 11 lists six operations (authorise, capture, void, refund, status,
  reconcile). On this wire, capture is folded into `authorise`, void is `reverse`, reconcile is
  `status` plus the day close, and `refund` exists on the wallet rail only.

**A Reverse Answer:** `{v, site, reference, outcome, amount_minor?, currency, reason?}` — `currency`
is required and must equal the one asked, as on every money answer.

- `approved` = the reversal succeeded, and it carries `amount_minor` (what was given back). The
  core's grader requires an amount on every `approved`.
- ⛔ **`amount_minor` must EQUAL the amount sent**, with ONE exception (next bullet). The amount sent
  is the amount the core holds, **or, on a Mismatch, the amount you captured** (your own `approved`
  told us; our app reads it from the core's record of your answer). Anything else is a violation: our
  app returns it as `unknown` — an answered non-`approved`, which costs one of five attempts — and at
  the fifth a person is told. The core's own reverse path never compares the amount, so our app is
  where this is enforced.
- **A reference the connector never received** (our app sent no `auth_ref`):
  - if the connector **can prove** that **nothing was captured** for the reference (never received,
    or a request it cancelled before any money moved), and its certified declaration attests
    `can_prove_absence` for the rail, it answers `approved` with `amount_minor` **0** (nothing to give
    back). This is the exception to the equality rule, and it is honoured only on those two
    conditions — ⛔ **never when our app sent an `auth_ref`**, because then an approval exists;
  - if it **cannot** prove it, it answers `unknown`.
- **What the core does with an answered reversal that is not `approved`:** `declined`, `pending` and
  `unknown` alike cost one of five attempts, re-sent every five minutes; at the fifth a person is
  told (adapter contract §13). **Only a reversal that gets NO answer keeps the budget** (no answer, a
  5xx, a 429). ⇒ **Make `reverse` idempotent by (`site`, `reference`) and finish it within the five
  sends where you can.** ⚠ While a reversal is in flight the core still treats the authorisation as
  live.
- Reversing twice must be safe, and must answer `approved` again.

**A Refund Answer** (the wallet rail only): see §3a items 4 and 5.

**How our app maps what it did NOT get** (the partner cannot see this, but should know it):

| What happened | On `authorise` / `status` | On `reverse` |
|---|---|---|
| no answer in time (in total), connection refused or dropped, certificate failure, 5xx, **429** | `unknown` (`network_timeout`) — ⛔ never `declined` | **raised** — the core counts it *unreachable* and keeps its five-attempt budget for when you are back |
| a reverse answered `pending`, `unknown`, `declined`, or `approved` with the wrong amount | — | **returned as answered** (an `unknown` for the wrong amount) — it costs one of five attempts, then a person |
| 401/403 (our signature refused) | `unknown` (`config_invalid`) | **returned** as `unknown` (`config_invalid`) — a permanent configuration refusal must end at a person, ⛔ not retry for ever |
| a violation (another reference, another `site`, a missing amount, an unknown outcome) | `unknown` at a live till; a **FAIL** in the conformance kit | returned as `unknown` |

## 5. The declaration — data, graded like a class

```json
{"v": 1,
 "display_name": "Acme Pay",
 "markets": [["KE", "mobile_money"]],
 "rails": {"mobile_money": {"settlement": "asynchronous", "can_prove_absence": true}},
 "capabilities": ["reverse"],
 "supports_refund": false,
 "payer_required": true,
 "certification": {"KE|mobile_money": "required"}}
```

- Our app builds one adapter per connector from this and hands it to the core's own
  `adapter_contract.declare()`, so the refusals and their order are exactly the adapter contract's
  §4.
- **The provider key is `remote_<partner>_<connector>`** (one form, used in the verdict too), unique
  per connector, so the core's registry, its foreign-tender refusal and `resolve()`'s provider
  scoping see each partner as a distinct provider.
- **One rail per connector.** A partner serving two rails publishes two connectors (the core cannot
  re-derive a multi-rail row's rail safely). Off the wallet rail, `capabilities` is exactly
  `["reverse"]` with `supports_refund: false`; on the wallet rail, see §3a item 1.
- ⭐ **The tenant runs the CERTIFIED declaration, not the live answer.** A tenant cannot widen
  `can_prove_absence` or a market by editing a record, and no release of ours is needed for a new
  partner.
- ⭐ **The certificate.** Its format is `{v, kid, payload: {provider_key, partner, connector,
  declaration, issued}, signature}`, Ed25519 over the canonical JSON of `payload` (sorted keys, no
  spaces, ASCII); `issued` is a full UTC timestamp. The **public keys are compiled into
  `ivendnext_pay_remote`**, so a tenant cannot swap the verifier. The certificate is stored on the
  tenant's `Remote Connector` record and **re-verified at every save and every load**; an edited
  certificate is a named refusal. A record refuses a certificate issued before the one it holds, and
  a compiled withdrawal list retires a certificate by release. A test key verifies only on a test
  bench (§1).
- ⭐ **Who issues a production certificate.** A CitiXsys **certificate service** issues it
  automatically from a sealed, `CERTIFIED` kit report (§9), signing with a key held in a cloud key
  service — ⛔ never held by a person, and never in a repository, a tenant or a bench. ✅ **Live since
  2026-10-13:** `POST https://library.ivendnext.app/v1/payment-certificate` with the downloaded report,
  unchanged, returns the certificate under key id `paycert-1`, whose public half is the one production
  key in `ivendnext_pay_remote`. Its refusals, the partner-to-site binding and key rotation:
  `PRODUCTION_CERTIFICATES.md`.
- **While a payment is live**, a newer certificate may not change the rail or the markets, nor widen
  `can_prove_absence`. Narrowing is always allowed.
- **Certification always runs the runtime path.** A stricter "raise on a violation" mode may exist
  inside the kit only, ⛔ never selectable by a tenant.
- A connector on a card-present rail is addressed by the till's terminal binding: `device` carries
  the terminal's wire address and `TERMINAL_TRANSPORT` is `cloud`.

## 6. Callbacks — the partner calls US

`POST https://<tenant>/api/method/ivendnext_pay_remote.api.callback?connector=<key>`. It is signed
with the connector's secret (the same scheme as §1), and its body is `{v, site, connector,
reference, answer: <an Answer>}`. Our app refuses a callback whose `site` is not its own.

Our app does four things:

1. verifies the signature, rejecting with **401** before the body is parsed (an over-size body is refused first, with 413);
2. checks that `answer.reference` equals `reference`;
3. puts the answer through **the same §4 validator as a status answer** (an `approved` without
   `amount_minor` or `auth_ref` is refused: an omitted amount would read as 0 → a mismatch → an
   automatic reversal of a real capture), converting with the **transaction's** currency;
4. calls the core's `resolve()` **in-process** and relays the result `{acknowledge, reason,
   status}`, wrapped by the platform as `{"message": {...}}`. An unknown or switched-off connector
   answers 401 exactly as a bad signature does. A callback never carries an absence (`exists: false`
   is refused): `resolve()` never voids on one.

⛔ **Never call back about a REFUND reference** (`MPOS-RFD-…`): a refund is settled by our `status`
question; such a callback is answered `422 unknown_reference` and is not an alarm.

⛔ **Retry only when `reason` is `in_flight` or `indeterminate`.** Stop on `acknowledge: true`. Raise
an alarm on everything else (adapter contract §12.3: `acknowledge` is true for exactly two reasons).
A callback is the fast path; the core's poll is the guarantee.

## 7. Profiles

- **`wallet`** — a partner's stored-value wallet: this contract with `preview`, `refund` and
  `payer_code` (§3a), on its own `Wallet` tender type. The cap is checked before the call, and
  refunds go only to the same wallet.
- **`card`** — `card_present`, synchronous, addressed by device, `can_prove_absence` as the provider
  allows.
- **`push`** — `mobile_money` or pay-later (`card_not_present`), asynchronous, `pending` + handle,
  with the customer leg on the payer's own phone.
- ⛔ **No new rail.** Pay-later rides `card_not_present` unless a market's certification differs.

## 8. Driver at the store (phase 2) — the agent shape

A counter-wired terminal needs a program beside it. **The store agent dials out** to the connector or
to a CitiXsys relay, and holds the connection with a heartbeat. It must **journal each request
before sending it to the terminal**, so that `status` can answer. A terminal that can approve
offline makes `can_prove_absence` **false**, so a lost answer goes to a person and is ⛔ never voided
automatically. ⛔ The tenant never calls the store.

## 9. Certification and versions

- **The kit.** The core's conformance kit runs unchanged against the connector through our app, on
  the partner's **hosted sandbox site** — the kit imports the core, and a partner gets no local
  bench. The partner starts it from a button on its connection there (a test bench only, a Remote
  Connector only); the bench command `conformance.run_for_connection` drives the same run. The kit
  is at **version 5** and runs **21 scenarios**: the adapter contract's sixteen (§14.3 of that
  document), plus the kit's own 17–21. For a connector, 18–20 are owed by a wallet (each must
  `PASS` for a declared operation to certify); 21 applies only to a `reverse` that declares the
  account, which `ivendnext_pay_remote` does not, so it is `N/A`. See
  `CONFORMANCE_KIT.md`.
- **The connector implements `induce`/`settle` on its sandbox copy.** Without `induce`, three of the
  four money-safety scenarios cannot run and the verdict is capped at `INCOMPLETE`.
- **The report is sealed.** It carries an HMAC-SHA256 seal made with a key on the sandbox bench that
  a tenant cannot read, and it names the site, the connector, the certificate payload tested, the
  wire version, the versions of the core and of our app, and every scenario. ⚠ The seal proves the
  kit wrote the report on that bench; ⛔ it does not prove who ran it, so the report's site and
  partner code is bound by the certificate service to the first site it certifies from (§5;
  `PRODUCTION_CERTIFICATES.md`).
- **Going live.** A connector is certified when the kit reads `CERTIFIED` on the partner's hosted
  sandbox and the sealed report says so; the production certificate (§5) is then issued from that
  report. **No pilot store is required.**
- **Versions.** `paygw/1` is supported in the current version and the one before. Additive changes
  do not bump it. A core release does **not** re-certify a connector unless the wire version moves.

## 10. What this revision does NOT do

- No inbound receipts (adapter contract §16b).
- No disbursement.
- `refund` exists on the wallet rail only. A card refund is still made on the provider's machine and
  recorded at the till.
- **No `merchant` on `reverse`.** The core can tell an adapter's `reverse` the account when that
  `reverse` declares an optional `account` parameter (adapter contract §11.2;
  `BUILD_A_GATEWAY.md` §5). `ivendnext_pay_remote` does not declare it, so a
  `reverse` on this wire carries no `merchant`, and the connector resolves the merchant from its own
  record of (`site`, `reference`). `status` is told the merchant on the connection test only (§3).
- No database for a CitiXsys-hosted connector until hosting has one. A connector whose provider
  cannot be looked up by our reference cannot be hosted by us before then.
- ⚠ "An asynchronous rail answers `pending` within 10 s" is a **partner obligation our app does not
  enforce** — every rail's `authorise` has the one 60 s deadline.

---

## Revision history

| Revision | Date | What |
|---|---|---|
| 1.0, note | 2026-10-13 | The certificate service is live (§5, §10). No change to the wire |
| **1.0** | 2026-10-13 | **APPROVED.** Draft v0.3 as built, plus: the `reverse` account statement corrected — the core can tell a `reverse` the account when it declares the optional parameter; our app does not, so the wire carries no `merchant` on `reverse` (§1, §10); the kit stated as built, version 5 with 21 scenarios (§9); no pilot store before going live (§9); production certificates issued automatically by a CitiXsys certificate service, not yet built (§5) |
| draft v0.3 | 2026-10-11 | The wallet profile: `preview`, `refund`, `payer_code`, `invalid_code`, kit scenarios 18–20 |
| draft v0.2 | 2026-10-11 | Amended to what was built in `ivendnext_pay_remote`: the indeterminate reversal settled (an answered non-`approved` reversal costs an attempt); a Mismatch reversed for the amount captured; `verb` inside the signed body; `site` required on every answer; one rail per connector; the certificate format; one deadline per verb, in total; the callback wrapping; `merchant` on `status` for the connection test only; the site id set once |
| draft v0.1 | 2026-10-11 | Written from an executed spike |
