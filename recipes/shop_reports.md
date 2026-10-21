# Recipe: reading the shop's own reports

**What it is for.** Your service needs a figure the shop already has a report for: stock by store, a stock balance over a period, sales by item. You run the shop's own report, with its filters, and read its rows, rather than rebuilding it from records. The shop's report stays the one source of the figure. From iVendNext POS build 2.0.0.654.

**The short version.**
- Run a report with `run_report`: the report's name and its filters. You get its columns and rows, as Desk shows them.
- Some reports the shop runs in the background (a *prepared* report, such as *Stock Balance*). For those, `run_report` never starts a run: it answers the last finished run for those filters, or nothing. Queue a run with `prepare_report`, wait for it, then read it.
- **What the shop must know before it gives you a key**, said plainly:
  - `run_report` reads **as the user the call names**. A call that passes `user` reads that user's view of the report: their report rights, their filters and their User Permissions, not your service's.
  - A run named by its record name (`prepared_report_name`) is read whole, whoever made it.
  - `prepare_report` checks no right. Any signed-in user may queue any report, and the run reads with their own User Permissions only.
  - So: never pass a `user` or a run name the shop did not choose, and give your service's user only the reports and stores it needs.

---

## Technical notes

### 1. Run a report

```
POST /api/method/ivendnext_mpos.api.v1.run_report
  {"report_name": "Total Stock Summary", "filters": {"company": "Demo Retail", "group_by": "Warehouse"}}
```

The answer's `message` holds `columns` and `result` (the rows). The filters are the report's own, as its filter bar in Desk names them; a required filter left out is refused in the report's words. A report the shop has switched off is refused (*Report … is disabled*). Every HTTP method is accepted.

### 2. A prepared report

```
POST /api/method/ivendnext_mpos.api.v1.run_report
  {"report_name": "Stock Balance", "filters": {"company": "Demo Retail", "from_date": "2026-01-01", "to_date": "2026-10-21"}}
→ {"message": {"prepared_report": true, "doc": null, ...}}            # no finished run for these filters yet

POST /api/method/ivendnext_mpos.api.v1.prepare_report
  {"report_name": "Stock Balance", "filters": { …the same… }}
→ {"message": {"name": "<the run's record name>"}}                     # one new run on each call

GET /api/resource/Prepared Report/<the run's record name>             # poll until status is Completed (or Error)

POST /api/method/ivendnext_mpos.api.v1.run_report  { …the same as the first call… }
→ {"message": {"prepared_report": true, "doc": {"name": "<the run>", ...}, "columns": [...], "result": [...]}}
```

- `run_report` reads the last finished run **for those exact filters, owned by the user it reads as**. Change a filter and you need a new run.
- `prepare_report` inserts a record on every call, even a GET: queue once, then poll. Delete the run's record when you are done with it (its output file goes with it).
- To read one run by its name, add `"prepared_report_name": "<the run>"` to the filters.
- The run is computed in the background, as the user who queued it, with that user's User Permissions.

### 3. Rights, plainly

| Call | What it checks | What it does not |
|---|---|---|
| `run_report` | the caller's right to the report's record type; the filters the user may use | ⚠ a `user` named in the call: the report is read **as that user** (their filters and their User Permissions) |
| `run_report` with `prepared_report_name` | the right to run the report named in the call | ⚠ that the run belongs to that report or to the caller: a named run is read whole |
| `prepare_report` | nothing | ⚠ any signed-in user may queue any report and read its output, filtered by their own User Permissions |

These are the shop's own behaviours, exposed under iVendNext names; the names add no power of their own. A report's own code may check more, as the caller.

### What was proven where

- **A sandbox site** (2026-10-21, POS 2.0.0.658, the Administrator's key): `run_report` on *Total Stock Summary* answered 4 columns and 59 rows; on *Stock Balance* (a prepared report) it answered `doc: null` before any run; `prepare_report` answered a run's name, the run was *Completed* within seconds and owned by the caller; `run_report` then read it by its filters (60 rows, 16 columns) and by its name (60 rows); a second `prepare_report` made a second run. Both runs were deleted, and their files with them. A report switched off on the site was refused.
- **The product's own tests** (2026-10-16): a caller naming another user reads that user's last run; `prepare_report` queues for a user with no report right; the three documents built from their source; `ignore_permissions` dropped from a web call.
- **Not run on a sandbox:** a call naming another user, a user with fewer rights, a report's own extra checks.
