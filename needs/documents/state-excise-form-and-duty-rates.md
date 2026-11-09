---
id: state-excise-form-and-duty-rates
title: A state's excise form and duty rates
area: documents
topic: own-records-and-fields
asks: Our state's own excise return, with its lines, codes and duty rates, filled from our stock and ready to file
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/liquor_excise_returns.md
sample: samples/s62_liquor_excise_returns
request: -
related: liquor-excise-returns
verified: carried 2026-11-09 from S62's README and recipe · not run with a state's form
---
## What you build
A version of your own of S62, built on the figures the card *liquor-excise-returns* gives: volume (in litres or US gallons, as S62 already offers) and pure alcohol per duty class, per store and period, kept as filed. You add the state's form as the worksheet's print (its layout and line codes), and the duty as a rate per class or strength band, worked out from those volumes in the service. You tie each store to its state with a field of yours on the store (Warehouse), and each state's form and rates are a data set of yours, read from the state's own published form and rate table.

## Limits
- The card names no state's form, rate or deadline. Ask the customer which of its states asks it to file at all.
- S62 holds no rate: your service keeps each rate with the dates it applies from, so a past return is worked out at the rate then.
- S62's lock keeps the return's lines and summary as filed. Put your duty lines under the same lock (a save rule), or a filed return's duty can change.
- The figures are the books as they stand when the return is worked out. Close each till's last day of the period before midnight, or that day's sales fall in the wrong period; a late till sync changes the next return's opening, never a filed one.
- S62 makes one store's return a press; your version may make every store's from one press.
- iVendNext files nothing: a person or your service sends the state's electronic filing, and the state's own check of the figures is theirs.
- Not run with any state's form.

## Tell the customer
Your return's volumes come from your own stock, and your partner lays them out on the state's form with the state's duty rates once checked against the state's own page; a filed return stays as filed.
