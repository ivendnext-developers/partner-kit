---
id: donation-intake
title: Donation intake with a donor receipt
area: documents
topic: own-records-and-fields
asks: Donated goods taken in with the donor's details, by kind and condition, and a donor receipt given at intake
status: ready-with-limits
door: manifest
blocked-by: -
recipe: recipes/donation_intake.md
sample: samples/s57_donation_intake
request: -
verified: 2026-10-29 · bench
---
## What you build
A donation as your manifest's own record type: the donor (a customer, a name typed at the door, or no one named), the donor's address, the store and the day, and the goods by kind, count and condition. A workflow *Received → Receipt given* (or *Cancelled*), and a save rule that then locks the donor, the store, the day and the goods on every door, so the receipt holds. A print format gives the donor receipt under the retailer's own letter head, stating no value; a report lists the donations; a field on Stock Entry names the donation whose goods a Material Receipt takes into stock.

## Limits
- The receipt states no value: a valuation for a tax claim, or the UK's Gift Aid, is a version of your own.
- The donation is written in iVendNext Desk; a till key that takes it at the till is a version of your own.
- A manifest's notification goes only to the retailer's own users: e-mailing the receipt to the donor is the retailer's own Notification.

## Tell the customer
Each donation is recorded at the door with who gave what, and the donor gets a receipt that stays as it was given; the stock entry that takes the goods in can name the donation.
