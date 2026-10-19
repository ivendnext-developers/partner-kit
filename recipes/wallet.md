# A partner wallet at the till — the recipe

A **partner wallet** is a balance you keep for the shop's customers (cash back, store credit, points with a money value), spent at the till as its own payment method. The cashier taps the wallet's tile with a customer on the sale, sees the balance and the most this sale may use, enters an amount, and the sale is paid. Nothing of yours runs inside the shop: your service answers the till's questions over HTTPS.

**Reference implementation:** `samples/s22_customer_loyalty/` — *Member cash*, the cash back of a customer's own loyalty programme spent at the till ([its README](../samples/s22_customer_loyalty/README.md#member-cash-spending-the-cash-back-at-the-till)).

**When to use it.** The customer wants a balance they already keep, or that you keep for them, to pay for a sale. If the shop's own loyalty or gift cards do the job, configure them instead (chapter 4). On your sandbox, ask us to add the remote-wallet payments app first ([chapter 11](../guide/11_payments_fiscal_hardware.md)).

## The till's four questions

Your service answers four questions, each about one payment the till names by its reference:

| The till asks | You answer |
|---|---|
| **What may this sale use?** (preview) | whether this customer may pay with the wallet, the balance, and the most this sale may take. Nothing moves. |
| **Take this much** (authorise) | approved with the amount taken, or declined with a reason. The same reference asked twice is one charge. |
| **Give it back** (reverse: the whole payment; refund: part or all of it, under the refund's own reference) | approved with the amount given back. Never more than was paid. |
| **What happened to this reference?** (status) | the answer about exactly that payment or refund, or *never received*. Never the answer about another one. |

The till checks a good deal before it asks you: a customer on the sale, an amount within the most your preview allowed, two wallets together never above what is due. A return pays the wallet's share back to the wallet first. The wallet is never offered offline.

## Steps

All of this is done on your own sandbox, on its screens, as the site's administrator. Ask CitiXsys to install the remote-wallet payments app on your sandbox site (a new sandbox site does not carry it) and to switch on its payments test mode, without which the sandbox refuses a sandbox certificate (step 3) and a *test* account cannot go live (step 7).

1. **Write your service.** Copy S22's `service/wallet.py` and its signed route in `service/app.py`, and point them at your own balance. Key every money write on the reference, so a repeated call is one charge; keep one customer's balance to one till at a time (S22 uses a file lock per member, which holds only while one host answers: two hosts behind a load balancer need a lock they share, such as your database's).
2. **Sign your sandbox certificate** with [the sandbox certificate tool](../tools/sandbox_cert/README.md): your declaration (what your wallet does), your partner name and the connector's name, signed with the published sandbox key. The declaration's markets must include the two-letter country of each shop company that will take it, or go-live refuses (the sandbox's shop is a US company).
3. **Remote Connector → New.** Paste the certificate, your service's **bare address** (`https://<service>`: the shop adds `/paygw/1/<verb>` itself, so an address ending in `/paygw/1` doubles it and every call answers 404) and a signing secret you choose. Save. The form shows the **site id**.
4. **Give your service** the secret, the site id and a merchant reference you choose, and restart it.
5. **Payment Account** (provider: your connector, environment *test*, the shop's currency, the merchant reference, and a **liability ledger account** for the balance: going live refuses an account without one) → **Payment Connection** (rail *wallet*; *Certification required*: *not required* on a sandbox, and if a test already ran, the approver ticks *Change acknowledged*).
6. **Test connection.** It must pass. For two minutes after your service starts, S22 answers *Inconclusive* on purpose (a write from before the restart may still land): wait and press it again.
7. **Go live.** The payments app makes the wallet's payment method and names any till that still lacks it; it does not add the method to a till. Put the payment method on each till's POS Profile; where that POS Profile links a payment template, the till offers only the template's methods, so add it there too.
8. **Allow the wallet in returns** on the till's payment methods, and at least one other method too: a refund pays the wallet's part back first and the rest another way.
9. **A contact number only if your wallet asks the customer's phone.** A declaration with `payer_required: true` tells the till the customer approves on their own phone, so the till refuses the wallet for a customer with no mobile number or email on record (nothing is taken); the reference implementation's walk met exactly that. A wallet that asks nothing of the phone declares `false`, as S22 does: CitiXsys's payments team walked a wallet declaring `false` on our test site (with a customer who had a phone on record). A customer with no contact at all has not been tried with it.

### When your service is down

The till says the wallet did not answer, and the cashier takes another payment (the product's wallet page says so; not yet walked). If you also run a **check before payment** that runs before every sale ([recipe](rule_guard.md)), its declared down answer decides the rest: *refuse* stops **every** sale at every till while your service is down, wallet or not. That is the shop's choice to make, with you.

## Certification

On your sandbox, the **Run the conformance kit** button on the Payment Connection sends test payments to your connector and gives you a report to download and send to CitiXsys. **CERTIFIED** means every scenario the kit drove passed; **REFUSED** names the one that failed. **Today a production certificate needs a CERTIFIED report.** ⚠ A connector like S22's, which answers the kit's test verbs (`induce`, `settle`) with 403 as a live connector does, gets an **INCOMPLETE** report, which does not qualify: **ask CitiXsys** whether a wallet that refuses the test verbs has another route before you plan on a production certificate.

A production certificate is issued by CitiXsys from your report. You never sign one yourself.

## What is proven, and what is not

- **Walked on a sandbox till** (2026-10-12), with CitiXsys's private reference implementation that S22 is adapted from: the preview and the most the sale may use (there the balance, below the 50 % cap); an amount over it refused by the till; a sale paid with the wallet and cash; a partial return paying the wallet's part back first.
- **Not walked with the reference implementation:** `reverse` from a till (the payments team walked it on our test site with its own test wallet), the conformance kit against a wallet, the percentage cap itself, and the till's own *did not answer* sheet (with the service down, that walk's check before payment refused the sale first).
- **S22's own copy** has run only in its laptop tests.

## Technical notes

### The partner starter note

*A copy of CitiXsys Payments: the partner sandbox runbook, §4, written for this kit. Its one home is there; a defect here is a defect there: report it on the [feedback forms](../feedback/README.md).*

> **Building a payment connector: three things to get right before your first test**
>
> 1. **Name your connector in every call you make to us.** Send a `User-Agent` header such as `acme-pay-connector/1.2`. Some network edges refuse a request that carries a programming language's default signature, and your callback is then lost without an error. The payment is still found by our next status check, but more slowly.
> 2. **Your callbacks are signed exactly as our calls to you are.** Use the same secret and the same signature headers, and the callback address your sandbox shows on the connector's screen. A callback with a bad signature is refused with 401 and changes nothing. A callback about one of the test kit's payments is answered 422 *unknown reference*: expected, not an alarm.
> 3. **Reversing a payment twice must be safe.** We may send `reverse` for the same payment more than once, for example after a lost answer. Treat it as idempotent by (`site`, `reference`): the second request answers with the first result and moves no more money.
>
> **Then certify on your sandbox:** register the connector, press **Test connection**, then **Run the conformance kit**, and send us the downloaded report. We check its seal; you do not need us to run anything.
>
> **Technical notes**
>
> - **Your sandbox certificate.** `{"v": 1, "kid": "test-1", "payload": P, "signature": S}`, where `P` is `{"provider_key": "remote_<partner>_<connector>", "partner": "<partner>", "connector": "<connector>", "declaration": {…}, "issued": "YYYY-MM-DDTHH:MM:SSZ"}` (partner and connector: lowercase letters and digits, 2–24 characters), and `S` is the base64 Ed25519 signature over `json.dumps(P, sort_keys=True, separators=(",", ":"), ensure_ascii=True)` made with the sandbox key below. The declaration's fields are in the `paygw/1` contract.
> - **The sandbox signing key** (private half, base64): the value of `SANDBOX_PRIVATE_KEY` in [`tools/sandbox_cert/sign_sandbox_cert.py`](../tools/sandbox_cert/sign_sandbox_cert.py). It is public on purpose. It is accepted only on a CitiXsys sandbox, and every production site refuses it.
> - **A production certificate** is issued by CitiXsys from your sealed report. You never sign one yourself.

The kit names the key's place instead of printing it twice, so the two can never disagree; [the tool](../tools/sandbox_cert/README.md) signs with it.

### The wire

⚠ **The kit's copy of the product's wallet page, [`contracts/pages/wallet.md`](../contracts/pages/wallet.md), describes the till's side, not the wire your service answers.** Its message tables leave out `site` and `verb`, which every call to your service carries (with `v`), and `merchant`, which preview, authorise and refund carry (reverse does not, and status carries it only on the shop's *Test connection*, where you should check it: never refuse a reverse or a till's status question for want of one); the customer arrives on `authorise` as `payer.party`; and every answer must name its `site`, or it is refused. The gateway contract is in the kit: [`contracts/pages/paygw.md`](../contracts/pages/paygw.md), revision 1.0, whose §3a is the wallet profile (`wallet/1`); S22's `service/wallet.py` answers it, and the payments team's stand-in connector (`contracts/paygw/partner_stub.py`, profile `wallet`) does too. Money is in the currency's minor units with `currency_exponent` on every money call; every call is signed (base64 HMAC-SHA256 of `<timestamp>.<raw body>`, the till key's scheme) and carries its verb inside the signed body, so a body signed for one verb is refused on another route. S22's answers, and why each is shaped as it is, are in `service/wallet.py`'s opening comment.

### What S22's tests hold

Each is a laptop test with a canary that goes red when its rule is broken (`tests/canaries.py`): the cap; one charge per reference; never more than the balance; a refund never more than the payment has left, in several parts, each answered for itself; reversing twice is safe; status about the asked reference only, and *never received* only when it was not; a write that may still land is never *never received*; the lock; the route off until its secret is set, and its signature checked; and a sale paid with the wallet earning nothing unless the settings say so.
