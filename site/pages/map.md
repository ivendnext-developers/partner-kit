# What you can use: API endpoints, record types, fields and screens

The developer's map. One page answers the questions a developer asks before building on iVendNext: **which API endpoints can my app call, which record types and fields can it read and write, what does iVendNext call on my service, what can a manifest add, and which screens can I make?** Each part is a table that links to its detail, and each is built from the kit file that defines it: when a name or a quoted sentence leaves its source, the site's build fails until the map follows.

**The four parts:** [(a) iVendNext endpoints your app calls](#a-ivendnext-endpoints-your-app-calls) · [(b) endpoints iVendNext calls on your service](#b-endpoints-ivendnext-calls-on-your-service) · [(c) what a manifest can add](#c-what-a-manifest-can-add) · [(d) screens you can add](#d-screens-you-can-add) · and [every record type with its fields](site:records/index.html).

**Calls go three ways.** Your service calls iVendNext's endpoints at the retailer's own address, with your app's key (part a). iVendNext calls your service's endpoints at your one address, signed with that retailer's secret (part b). And your service may call an outside system with that retailer's own account for it, which iVendNext never sees. Everything inside the retailer's iVendNext is data your manifest declares (part c), never code.

## (a) iVendNext endpoints your app calls

Every API endpoint your service calls on a retailer's iVendNext: the record calls, the iVendNext methods, the event feed and reports. Built from [`api/openapi.yaml`](../../api/openapi.yaml) and [`api/README.md`](../../api/README.md).

{{map: calls}}

## (b) Endpoints iVendNext calls on your service

One row per extension point, from its contract page in [`contracts/`](../../contracts/README.md): when it fires, what it sends, what you answer, its time limit and what the cashier or user sees. How the extension points fit together, and how to ask for a new one: [chapter 9](../../guide/09_points_and_requests.md).

{{map: points}}

## (c) What a manifest can add

{{map: manifest}}

## (d) Screens you can add

The screens an app can show: on the till, in the back office (Desk) and on its own. Your JavaScript never runs inside our screens; your screens come through these doors (rule 4 of [chapter 3](../../guide/03_ladder_and_never_list.md)).

{{map: screens}}

## Record types and fields

Every record type an app commonly reads or writes, with each field: its type, whether it is required or read-only, and what it links to. [Record types: what your app can read and write](site:records/index.html).

---

**Next:** [Get started](start.md): your sandbox, your key and your first call.
