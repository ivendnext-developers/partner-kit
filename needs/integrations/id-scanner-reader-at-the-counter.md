---
id: id-scanner-reader-at-the-counter
title: An ID-scanner vendor's reader at the counter
area: integrations
topic: outside-systems
asks: We use an ID scanner from a vendor at the counter; its result should go on the sale
status: ready-with-limits
door: partner-page
blocked-by: -
recipe: recipes/partner_page.md
sample: samples/s17_partner_page, samples/s37_age_check
request: -
related: age-check-at-scan-and-pay, id-at-customer-add
verified: carried 2026-11-09 from the door's page and S37 · not run with a vendor's reader
---
## What you build
Your page as a key on the till (a sheet over the sale), beside the age check S37. The page shows the vendor's result, read through the vendor's own service or from a field the reader types into. When the reader passes the licence for the age the basket needs, your server answers once with the sale detail S37's check at Pay reads, such as *21 or over*, and the cashier confirms it on the till's sheet. Your server keeps the vendor's account and keys; iVendNext holds none.

## Limits
- From POS build 695 the till's own camera turns a US or Canadian licence into the age (the expiry shows beside it, nothing else is kept). A counter PC with no camera has no such read. A vendor's reader adds what the vendor sells, such as a check that the card is genuine and the vendor's own record.
- Never let a reader that types fill the till's own *Sale details*: the text is kept on the sale as typed, name and number included. Use your page's own field.
- The page runs in a frame with no camera, USB or serial access: the reader must reach your page through the vendor's service or by typing. Not run with any vendor's reader.
- iVendNext keeps the age band your page answers, never a date of birth or licence number. What your service or the vendor keeps is yours to settle with the customer.
- The cashier can still type the age in *Sale details*; S37 cannot tell it from the vendor's answer.
- If the page or the vendor is down, nothing is added: the cashier types the age and Pay accepts it. Offline the key is dimmed, and S37's own down answer applies.
- Counter and tablet only: the phone places no app keys. The key is placed in POS Studio, Apps.

## Tell the customer
The cashier opens the reader's page on the sale, and the vendor's result is recorded on the sale as the age band, never the licence itself. The till's own camera read stays as the way without the vendor.
