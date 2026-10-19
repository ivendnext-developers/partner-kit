# The project blueprint — fill it at the start of any project

**For:** an iVendNext Partner, a licensed customer's IT team or the CitiXsys Consulting Team starting a project for an iVendNext customer, before quoting it and before building. **Reference:** the ladder classes below, the extension-point catalogue (guide chapter 9, [The extension-point catalogue and requests](../guide/09_points_and_requests.md)), guide chapters 3 and 15 ([The ladder](../guide/03_ladder_and_never_list.md), [Customer archetypes](../guide/15_customer_archetypes.md)) and the feedback forms ([`../feedback/`](../feedback/README.md)).

A blueprint is one page per project that answers six questions: what does the project do, **which door does each need use**, how big is it, what does it connect to, which extra work does it switch on, and what could go wrong. It is the same page for a three-store shop and a fifty-store chain. **The needs decide what the project gets, never the customer's size:** "Standard" and "Enterprise" describe a customer, and they route nothing.

> **Download:** [the blueprint form](https://developer.ivendnext.com/downloads/blueprint_form.pdf) (PDF, at most four A4 pages, to print) · [how to fill it](https://developer.ivendnext.com/downloads/blueprint_how_to_fill.pdf) (PDF, one page) · [the template](https://developer.ivendnext.com/downloads/blueprint_template.md) (Markdown, to fill on screen; also [as a page](blueprint_template.md)). **See it filled:** [the blueprint example](blueprint_example.md), an invented chain of phone shops ([as a PDF](https://developer.ivendnext.com/downloads/blueprint_example.pdf), in the form's own layout, to print beside the blank one; [as Markdown](https://developer.ivendnext.com/downloads/blueprint_example.md)).

## How to fill it

1. Copy the template, [`kit/blueprint_template.md`](blueprint_template.md), into your project, or print [the form](https://developer.ivendnext.com/downloads/blueprint_form.pdf).
2. Write section (a) first. Then list every need in (b), one row each, in the customer's words.
3. Find each need's card in the [needs catalogue](../needs/README.md): `python3 tools/needs/needs.py search <the customer's words>`. `python3 tools/needs/needs.py blueprint <id> <id> …` prints the rows of section (b) for the needs that have a card: the verdict, the door and the limits. For a need with no card, place it on the ladder yourself, pick the door and the verdict from the table below, and name the nearest request class in the note.
4. Fill (c) and (d) with real figures, or with a stated guess. A guess is fine if it is marked as one.
5. Read (e) against the first four sections. Each module that applies is switched on, and its extra work joins the project.
6. Write (f). A risk you did not write down is one you will meet on the day.
7. Keep the blueprint up to date as scope changes. Attach it, or link it, to any [point request](../feedback/point_request.md), [sample request](../feedback/sample_request.md) or [kit defect](../feedback/kit_defect.md) that concerns the project.

**The verdict, in four words** (the needs catalogue's; a colour or icon may sit beside a word, never replace it):

| Verdict | Meaning |
|---|---|
| **Ready** | a developer can deliver it now with no code inside the tenant and no product change |
| **Ready, with limits** | the same, with limits you state in the row and tell the customer (for example *feed*: on the engine feed the integration user needs a broad role to read it; the door is scoped to one application) |
| **Not yet** | waits on an extension point we are building or you request (its name, as guide chapter 9 gives it, or its request handle, in the note), or on product work that is not an extension point: a feature of a pack, our payments or our fiscal apps; ask us |
| **Not possible** | it breaks one of the four rules (guide chapter 3); write what to do instead |

**The doors, in order:** configuration · outside app (the API and the event feed) · till key · manifest · sandboxed function · a request for an extension point, asked for only when no combination of the doors above meets the need. A rung is used only when the one above cannot do the job. The four rules (guide chapter 3) apply to every row.

---

## (a) The project in two lines

Say what the customer wants and what you will deliver, in business terms. If it takes more than two lines, it is two projects.

## (b) Fit-gap

One row per need. `python3 tools/needs/needs.py blueprint <id> …` prints the rows for the needs that have a card. The columns:

| Column | What goes there |
|---|---|
| **Need** | In the customer's words, one line. Not a mechanism. |
| **Card** | The need's card id in the needs catalogue, or *none*. |
| **Status** | One of the four verdicts above: the card's, or yours for a need with no card. A *Ready* or *Ready, with limits* row is one you have checked on your sandbox. |
| **Door** | The way in: *configure*, *outside app*, *event feed*, *till key*, *manifest*, *sandboxed function*, *our connector*, an extension point by its name from guide chapter 9, or *request* for a *Not yet* row. A row can use more than one. |
| **Limits and note** | Every limit on the card, which the customer must accept; for a *Not yet* row the extension point or request handle to ask for (or *point request sent*), or what to ask us; for a need with no card, the nearest request class (selling screen, print / receipt / label, ERP integration, back-office / stock / count, payment / tender, report / dashboard, fiscal, loyalty / gift / promo). |

⛔ A need that can be met only by breaking one of the four rules is not a row with a door. Rewrite the need ("what must be true for the customer") and place that.

## (c) Scale profile

The profile says how big the estate is and how hard it is pushed, in numbers a test can reproduce. The scale-profile kit (`tools/scale_profile/`) books real till sales on a bench and reports the profile against what it measured — and, every time, what it did NOT measure (concurrency, many stores, a large catalogue, offline drains). Its figures are sequential, and no load test exists anywhere else, so a stated profile is the only way anyone will know the estate was ever sized. `python3 tools/scale_profile/report.py <your profile.json> <the measurement>` turns this section into that report.

**Work out the peak.** From the figures above:

```
sales per day               = stores × tills per store × sales per till per day
sales in the peak hour      = sales per day × peak-hour share
sales per minute at peak    = sales in the peak hour ÷ 60
```

Do it once for the average day and once for the busiest day. Then check it against the known limits (below).

**Known limits to check your profile against** (guide chapters 15 and 16):

| Limit | Value |
|---|---|
| Largest live estate | 18 terminals |
| Load tests run | none |
| Our Acumatica connector | about 2.75 complete sales a minute per connection |
| ERPs per company | one |
| Company | one country and one currency |
| Handheld | books online only in its first release |
| Offline | the sales snapshot lasts 24 hours, the catalogue 72 hours, offline promotions 7 days |
| What is not offered offline | an answer from your service is not asked for on an offline till, unless it is a sandboxed function |

## (d) Integration map

One row per outside system. The **door** is the event feed, the API or a file. A system with two directions gets two rows.

- **Our connectors first.** Where one of our connectors fits (the online shop, the ERP), name it. A connector replaces a row of your own work.
- **Identity map.** Every sync that keeps records on both sides needs someone to hold the map of record ids. Say who holds it.
- **If the far side is down.** Say what waits, where, and what catches up. The event feed holds what you have not collected.
- **Who owns the far side** is a role ("the customer's IT team", "the ERP vendor"), not a person.

## (e) What this blueprint switches on

**The needs decide, not the size.** Each module below is switched on by something in sections (b) to (d), and by nothing else. The triggers are the proposed ones; a module you switch on adds work, and one you leave off is a risk to write in (f).

| Module | Switched on when | What it adds |
|---|---|---|
| **Joint extension-point lane** | a row is *Not yet* on an extension point (or has no card and needs a point request) and the project cannot go live without it | work with us on that extension point, from its specification to its first release, using the point-request form |
| **Scale proof** | any figure in (c) is above the known limits, is a guess you cannot back, or an integration leg's peak is near its known rate | the scale profile is run against a sandbox with the scale-profile kit before go-live, and the result is attached to the blueprint |
| **Release gate in the customer's CI** | the project reaches the sale or money (a till key, an extension point, a sandboxed function, a wallet), or the customer's IT team will own upgrades | the recorded baskets, the money kit and the self-check run in the customer's own pipeline, and are re-run before every upgrade |
| **Dedicated bench** | **CitiXsys Consulting Team only**, and only if embedded Python is the sole way to meet a need | a dedicated bench for that customer; the case also becomes a point request, so the next customer gets a door. An iVendNext Partner or a licensed customer's IT team never needs one. |

## (f) Risks and open questions

Write what you do not yet know, and what could stop the project. Use these prompts:

- A row's bound that the customer has not yet accepted.
- An extension point the project waits on, and what you do if it slips.
- A figure in (c) that is a guess.
- A far side whose rate or availability you have not seen.
- Offline: what the stores do in a long outage.
- What the customer's gate will refuse.
- A need you could not place.

Each item names what would settle it and who can answer. Items that are questions to us go to the right form.
