---
id: lucky-draw
title: A lucky draw for a campaign
area: customers
topic: loyalty-and-wallets
asks: One entry for every 200 spent during the campaign, then a fair draw of the winners
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/lucky_draw.md
sample: samples/s44_lucky_draw
request: -
verified: run on our test bench 2026-10-23 · the shop's own till sales and a return counted, drawn once, the draw refused before the last day and never repeated, walked in a browser as the campaign's manager
---
## What you build
A campaign record and two buttons on it: *Count entries* and *Draw winners*. Your service reads the campaign's till sales, counts each sale's entries net of its returns, draws the winners and reserves, and writes the results on the campaign.

## Limits
- Till sales only: a Desk sale or a web order does not count.
- A sale counts only when the cashier has added the customer; a sale on a till's walk-in customer is never an entry.
- Draw once every till has sent its sales: a sale that arrives after the draw is not in it.
- One press reads the whole campaign: split a campaign of more than about 50,000 sales by till.
- The customer's own entries are not shown at the till or on the receipt.

## Tell the customer
Every 200 you spend during the campaign is one entry; after the last day the winners are drawn, each entry with the same chance, and each winner wins once.
