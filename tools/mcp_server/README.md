# Our MCP server — iVendNext for an AI assistant, outside the retailer's iVendNext, on the person's own key

This server lets an AI assistant read iVendNext records — and, when the person says so, write them. It is for a customer's staff, an iVendNext Partner or the CitiXsys Consulting Team, with a paid assistant or a free open-weight model. **Bring your own AI.**

The server runs **outside** the retailer's iVendNext, acts with **the person's own key**, is **read-only by default**, and needs **an explicit confirmation for every write**. We never pay per query; nothing AGPL; no AI app in the retailer's iVendNext.

**When to use it:** you want an assistant to answer questions from, or make small changes in, a retailer's records with the same rights the person has in Desk.

## Run it

1. Run it for an AI desktop app (stdio), with the person's key:

   ```bash
   IVN_BASE=https://shop.example IVN_KEY=… IVN_SECRET=… python3 tools/mcp_server/server.py
   ```

2. Or run it over HTTP on the local machine, with writes allowed and an audit log:

   ```bash
   IVN_BASE=https://shop.example python3 tools/mcp_server/server.py --http localhost:8130 --writes --audit mcp_audit.jsonl
   ```

3. After the API description changes, regenerate the tools:

   ```bash
   .venv/bin/python tools/mcp_server/generate.py
   ```

## How it works

- **Generated from the API description.** `generate.py` turns every operation in `api/openapi.yaml` into one tool (24 today: 19 read, 5 write) and writes `tools.json`; the server reads that file. A new operation in the description is a new tool after one re-run; a test fails if `tools.json` is stale.
- **Standard library only** (Python 3.9+). No third-party code, so no licence question.
- **Two transports.** *stdio* — an AI desktop app starts it and passes the person's key in its environment (`IVN_KEY`, `IVN_SECRET`). *HTTP* — `--http localhost:8130`, JSON-RPC on `POST /mcp`; **each request brings the person's own `Authorization: token <key>:<secret>`**, which the server forwards to iVendNext and never stores.
- **The retailer decides.** The server holds no key of its own. Every call goes to `IVN_BASE` with the person's key, and the retailer's permissions apply as they would to that person in Desk.

## The write guard

1. **Read-only by default:** write tools are not even listed unless the server's operator starts it with `--writes`; a write call to a read-only server is refused.
2. **Every write needs `confirm: true`.** Without it **nothing is sent** and the answer is a preview of the exact write (method, address, body) for the assistant to show the person.
3. **What the server cannot check:** the server cannot see a person. The assistant must ask before it sets the flag; assistants that prompt before a tool call do so for every tool marked destructive (the writes are). Treat `confirm` as the assistant's promise that the person said yes. **Writes act as your key:** you are responsible for what your assistant does with it.

## The audit log

One JSON line per tool call (`--audit`, default `mcp_audit.jsonl`): time, transport, **a key fingerprint** (first 4 characters + a hash — never the key or the secret), the tool, method and address, **the argument names (never their values)**, confirmed or not, the retailer's status.

## Profiles

`--profile file.json` narrows the server for one kind of person: the **tools** it lists (with the words the assistant reads for each) and the **record types** the general record tools may read or write. It can only take away, and the retailer's permissions for the key still decide. A tool or record type outside the profile is refused by the server before iVendNext (the log says so). Two profiles for a store manager — read-only, and with one write (switch a promotion, change a price row) — are in `samples/s10_ai_manager/`; recipe `recipes/ai_manager.md`.

## Before you rely on it

- The HTTP transport binds to the local machine. Put it behind HTTPS before anyone else reaches it.
- It knows only the operations in `api/openapi.yaml`. Widening the description widens the server.
- It has been tried with a script playing the assistant, not with a real AI model.

## Technical notes

### Proven (2026-10-04)

- **Laptop, 14 tests** against a fake iVendNext: read-only by default; an unconfirmed write sends nothing; a confirmed write carries the caller's own key; no key → refused before iVendNext; arguments checked against the schema; a path value cannot escape its segment; **no redirect is followed with the key** (this test found a real defect — a redirect was reported as a success — fixed); the audit log holds no secret and no value; stdio and HTTP end to end; standard library only.
- **Bench, 18 checks, two real keys of different roles:** the stdio server lists 19 read tools and refuses a write even when confirmed; over HTTP with `--writes`, an unconfirmed write is refused with a preview and nothing is written; the writer's confirmed write lands (exactly one comment); **the reader's key, confirmed, is refused by iVendNext (403) — a key cannot exceed its person's role**; neither key may book stock or read customers (their roles say so); the audit log has one line per call and no key, secret or argument value.

### Bounds

- Tested with a script playing the assistant; no AI model was connected.
- The HTTP transport is plain JSON-RPC (no server-sent events, no sessions) and binds to the local machine; put it behind HTTPS before anyone else reaches it.
- It knows only the operations in `api/openapi.yaml` — today, the ones the samples use. Widening the description widens the server.