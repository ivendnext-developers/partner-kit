# S49 — Post-sale feedback (`pp_psf`): ask each customer how their visit was

The retailer wants its customers' own word on each store. After a till sale, the retailer's own message asks the customer how the visit was, with a link to a one-page answer: three answers in the retailer's words, an optional comment, and *Stop these messages*. Each answer lands on the retailer's own record of that sale's request, once, and a report lists the answers by store.

**When to use it:** the retailer wants answers kept in iVendNext, by sale and store, sent through its own SMS gateway, e-mail account or WhatsApp app.

## What happens

| When | What happens |
|---|---|
| A manager presses *Send feedback requests* on a rule | The service reads the rule's till sales of its days received since the last press, and makes one request per customer to ask. The press's answer says how many, and why the others were not: *already asked*, *asked us to stop*, *with no mobile number or e-mail* |
| A request is made | The retailer's own Notification sends it by SMS, e-mail or WhatsApp, with the customer's own link |
| The customer opens the link | The retailer's name, the sale's date, the question and three answers in the retailer's words; a comment; *Stop these messages* |
| The customer answers | The answer (kept in English: *Satisfied*, *Neutral* or *Not satisfied*), the comment and the time are written on the request, which reads *Answered*. A second answer changes nothing |
| The customer ticks *Stop these messages* | Written on the request, with or without an answer; no press asks them again |
| A link past its last day | *This link has closed.* No answer is taken |
| A guessed or altered link | *This link does not work.* The retailer's iVendNext is never read |
| The store's walk-in customer, a return, a sale with no customer | Never asked |
| A customer asked already in the rule's days | Not asked again, whichever rule asked |
| More sales than one press can make in its 10 seconds | It makes what fits and says *More sales wait: press again.* The next press starts where it stopped |
| The service down | The button's own words: *Send feedback requests did not answer in time. Check the record before you try again.* Nothing is written (measured on the programme's bench) |

## What iVendNext does

1. **Install the app** from the App library (or paste its manifest into **Retail Extension Package** in Desk), read what it will do and consent. It comes in switched off: its service has no consent and is off, and its button is off. The install adds the record types *PP PSF Rule* (and its table of POS Profiles) and *PP PSF Request*, the report *PP PSF Answers*, and makes the roles **PP PSF Manager** and **PP PSF Integration**.
2. **Make the app's integration user** (the [integration user recipe](../../recipes/integration_user.md)): tick *Is Desk User*, give it the role **PP PSF Integration** alone, no User Permissions, and generate its API key. In *Role Permissions*, give that role **read on POS Invoice, POS Profile and Customer** (the service reads the till sales, each POS Profile's walk-in customer and store, and the phone and e-mail of a customer whose sale carries none). The install gives the role its rights on the app's own record types. Choose the user on the feed registration **PP PSF Feedback feed**, then press **Connect again** on the app's record, which sends that user's key to the service.
3. **Give your managers the role PP PSF Manager.** It keeps the rules, presses the button and reads the requests and the report. In *Role Permissions*, give it **Select on POS Profile**, for the rule's table of POS Profiles (a System Manager too, where the site removed it).
4. **Let iVendNext send the message.** For a text: in **SMS Settings**, your SMS gateway's address and its parameters. Then make one **Notification**: *Document Type* **PP PSF Request**, *Send Alert On* **New**, *Channel* **SMS**, a recipient *Receiver By Document Field* **mobile**, and a message holding the link, for example `Thank you for shopping with us. How did we do? {{ doc.link }}`. For e-mail, the same with *Channel* **Email** and the field **email**; for WhatsApp, the WhatsApp app's notification on the same record. Save it switched on.
5. **Write a rule** in *PP PSF Rule*: the name your customers read (your brand, or the store's), the question and three answers in their language, the days back a press reaches (1 to 7; 1 means yesterday's and today's sales), the days a link stays open (1 to 30) and the POS Profiles it covers (none: every POS Profile).
6. **Switch the service and the button on:** **Retail Extension Subscription**, the record *Post-sale feedback*: read what it is sent, tick the consent, switch it on. Then **Retail Desk Action**, the record *Send feedback requests*: switch it on.
7. **Test it:** ring a sale for a customer with your own mobile number, open the rule and press *Send feedback requests*. A text with the link must reach your phone, and your answer must show on the request. If no text arrives, check the SMS Settings, the Notification and the Error Log.

**Where it shows.** In Desk: the rules' list and form, with the button on both; the requests' list (its sidebar counts by store and answer) and form; the report *PP PSF Answers*. At the till: nothing new. The customer sees the message and the page.

**What leaves the retailer's iVendNext.** On each press, the retailer's server sends the service the pressing user's login and language and the pressed rules' names. The service then reads, with the integration user's key: the rules, every POS Profile's walk-in customer and store, the rule's till sales of its days (each sale's name, customer, customer's name, contact mobile and e-mail, POS Profile, date and when it arrived), the requests already made and the customers who asked to stop, and the mobile number and e-mail of the customers whose sale carries neither. It writes one request per sale to ask, and each rule's *Asked up to*. The message goes from the retailer's own server through its own gateway. The customer's page sends the service the link's two parts and the answer, comment and *stop*; the service reads that one request and its rule, writes the answer, and shows only the rule's name, the sale's date, the question and the answers. It keeps nothing of a call. A hosted copy holds each retailer's press secret and its user's API key from *Connect again* until the retailer removes the app. Say so on your card.

## The files

| File | What it is |
|---|---|
| `manifest.json` | the record types `PP PSF Rule` (named by its title), its table `PP PSF Rule Profile`, and `PP PSF Request` (named by the sale; the integration role writes it, the manager reads it), the report, two help addresses, a feed registration (it names the app's one integration user), one `desk_action` service and the button *Send feedback requests* on the rule's form and list for the manager; installed **switched off** |
| `feedback.py` | the pure core: the press's signature (`verify`) and records (`rules_of_press`), a rule (`rule_of`), whom to ask (`choose`), where the next press starts (`mark_after`), the contact (`phone_of`, `email_of`, `contacts_of`), the signed link (`link_of`, `sale_of_token`), the request (`request_of`), the press's answer (`press_answer`), the page (`page_of`) and the customer's answer (`answer_of`) |
| `service/app.py` | the service, standard library only: `POST /psf/send` (the press), `GET /` with `page.js` and `page.css` (the customer's page), `POST /psf/open` and `/psf/answer` (its two calls), `GET /health`, and the app template's handshake for many retailers; one `handle` answers the web server and the function entry (`lambda_handler`) alike |
| `service/page.html` · `page.js` · `page.css` | the customer's page: no inline script, no outside source; its own words in English, Arabic or Spanish by the phone's language |
| `Dockerfile` · `app.json` | the settings file for hosting (`"runs": "function"`: on CitiXsys hosting it is a function, paid per call) and an image for your own server (built from the kit's root) |
| `tests/` | the core, the service over the wire with signed presses and the page's calls (one retailer and many), iVendNext's reads and writes against a stand-in iVendNext, every answer against the published contract, the manifest; `canaries.py` breaks each guarded rule and expects its test to fail |

## Run it

```bash
python3 -m unittest discover -s samples/s49_post_sale_feedback/tests -p 'test_*.py'
```
```bash
python3 samples/s49_post_sale_feedback/tests/canaries.py
```
```bash
python3 samples/s49_post_sale_feedback/service/app.py samples/s49_post_sale_feedback/service/.env.local
```

**Settings, one retailer** (`service/.env.local`, never committed): `IVN_SEND_SECRET` (handed back at install as `pp_psf:sub:send`), `IVN_SHOP_URL`, `IVN_SHOP_KEY` (`<api key>:<api secret>` of the integration user), `PSF_PAGE_URL` (where customers reach this service's page: its links point there), `PORT`. `PSF_PREFIX` names the record types (default `PP PSF`).

**Before you install:** every `host.docker.internal` address in `manifest.json` (in `allowed_urls`, and where the manifest calls it) is our test bench's own address for the sample's service, and it resolves only where Docker provides it. Replace it with your own service's address first, or iVendNext's presses never reach your service; if this manifest is already installed, raise its `version` and install it again ([the manifest recipe](../../recipes/manifest.md), step 6).

## Many retailers, hosted

The service is the [app template](../../tools/app_template/README.md)'s shape: set `IVN_LIBRARY_APP` and a store (`IVN_SHOPS_TABLE` on CitiXsys hosting, else `IVN_SHOPS_FILE`). Each retailer connects itself after its install and hands over the press's secret; *Connect again* hands over its integration user's key. Until the key arrives a press is answered in words. Every press names its retailer's iVendNext (`X-iVendNext-Site`); every link names it too (`s`), signed with that retailer's own secret, so a link opens only for its own retailer.

## Make it your own

What a partner usually changes:
- **the answers:** a score out of five or ten, or a second question (the answer field's options and `feedback.ANSWERS`);
- **the channel:** WhatsApp's own reply buttons through one provider's API, called by your service (then the customer's number passes through your service: say so on your card);
- **who is asked:** only sales above an amount, or only some customer groups (read them with the integration user, which then needs read on what holds them);
- **the prefix:** `tools/manifest/rename.py` makes your copy under your own reserved prefix in one step; the service takes its prefix from `PSF_PREFIX`;
- **its records:** `tools/deploy/copy_records.py` moves the rules between a test site and the retailer's iVendNext.

## Before you copy it

- **A press, not a schedule.** The messages go when a manager presses. On CitiXsys hosting a function has no schedule yet; when it has one, the same press handler runs on it unchanged.
- **The phone and e-mail are the retailer's.** The sale's own contact first, else the customer's record: a customer the till creates holds its phone and e-mail in the till's own fields (`custom_phone_no`, `custom_email`), never *Mobile No*, and its sale carries no contact (measured on the programme's bench). A customer with neither is counted and never asked.
- **The link is the key.** Anyone who has a customer's link can answer for that sale, once. Ticking the button's consent again changes the secret: links already sent stop working.
- **No message, and no error in Desk:** a Notification switched off sends nothing, SMS Settings with no gateway address only print a message, and a gateway that refuses is written to the *Error Log*; in each the request is made and the customer gets no message. The setup's test step catches the first two; watch the Error Log for the third.
- **A slow gateway slows the press.** The message goes inside each request's save; the service saves eight at a time and stops starting new ones 4.5 seconds into the press. The rest wait for the next press.
- **A new key.** A key withdrawn or a user disabled (401 or 403) is said in words at the press until the user is switched back on or given a new key, and *Connect again* sends it.
- **Your address.** Write your own address in `allowed_urls` and `PSF_PAGE_URL`. The retailer's server must trust your certificate: a real one for a retailer.

## Technical notes

### Why it is built this way

| Option | Cost | Verdict |
|---|---|---|
| Do nothing | 0 | no answer from any customer; the retailer guesses how its stores do |
| A survey tool's link in the retailer's receipt message | about 10 lines of setup | answers live outside iVendNext, by no sale or store, with no stop and no one-answer rule |
| A container reading the event feed, sending at each sale | about the same code, and a container's monthly cost | a press once a day does the same journey at no standing cost |
| The retailer's Notification on each sale with a value of the till's own as the link's secret | about 250 lines, no press | rests on a hidden till field no contract documents |
| **A press that makes one request per recent sale, the retailer's Notification sending each, a signed link to a page the service serves** | about 600 lines of core, service and page with their docstrings | **picked**: kit doors only, a function paid per call; S44's press shape and S24's page reused |

### The answer, exactly

- **The press's reads**, each with its own timeout inside the press's 7 seconds: `GET /api/resource/<prefix> Rule` with `fields` `["name","enabled","shown_name","question","answer_good","answer_ok","answer_bad","look_back_days","open_days","asked_up_to","profiles.pos_profile"]`, `filters` `[["name","in",<the pressed rules>]]`; `GET /api/resource/POS Profile` with `["name","customer","warehouse"]`; for each rule `GET /api/resource/POS Invoice` with `["name","customer","customer_name","contact_mobile","contact_email","pos_profile","posting_date","docstatus","is_return","creation"]`, `filters` `docstatus` 1, `is_return` 0, `posting_date` from the rule's first day, its POS Profiles, `creation` at or after its *Asked up to*, `order_by` `creation asc`, `limit_page_length` 500; `GET /api/resource/<prefix> Request` with `["name","customer"]` for those days, and with `["customer"]` for `asked_to_stop` 1; `GET /api/resource/Customer` with `["name","mobile_no","email_id","custom_phone_no","custom_email"]`, fifty names a read. A read past the press's time answers 502: nothing is written.
- **The writes:** `POST /api/resource/<prefix> Request` per sale to ask, eight at once, none started after 4.5 seconds, each given 2 (a duplicate counts as made; a 400 or 417 is counted and never tried again; anything else is tried by the next press); then `PUT /api/resource/<prefix> Rule/<name>` with `asked_up_to`: the first sale not made, else the last sale read.
- **The link:** `PSF_PAGE_URL/#s=<site>&t=<sale>.<sig>`, `sig` the first 22 base64url characters of HMAC-SHA256 of `psf1|<site>|<sale>` with the press's secret.
- **The page's calls:** `POST /psf/open` and `POST /psf/answer` with `{"s", "t"}` (and `answer` 0 to 2 or none, `comment`, `stop`). A bad signature, or a site the service does not know: 404 `{"state":"unknown"}` before any read. Then `GET` the request and its rule; on an answer, `PUT` the request with its `modified` as read (a refused stale write shows what the other tap saved). The answer is `{"state": "open" | "answered" | "closed", "name", "date", "question", "answers", "stopped"}`; the retailer's iVendNext down, 503 `{"state":"unavailable"}`.

### Bounds, stated

- **The till's sales only:** POS Invoice. A sales invoice made in iVendNext Desk is not asked.
- **Offline sales** are asked once they reach iVendNext: the press reads by when a sale arrived.
- **Days are UTC's:** a rule's days and a link's last day are counted on UTC's date, which can differ from the store's by a few hours.
- **A save sent whole with no answer in time** is counted *could not be made* and tried again by the next press, which finds it made.
- **Requests stay** (the manager role and your System Manager read them) until the app is removed; the uninstall's export file keeps them. Each holds a customer's mobile number and e-mail: a System Manager can delete older ones from the list.
- **Where it runs:** the App library's copy runs in CitiXsys hosting's US region. The first press after a quiet spell starts the function (1 to 2.5 seconds, measured on earlier apps), inside the button's 10. The press's reads go side by side, in three rounds, so a retailer far from the US waits about three round trips before the writes.
- It logs one line per call: the route, the status and the milliseconds, never a body, a link, a number or a key.
