<!-- Source: ivendnext/partner-programme spikes/wasm/CONTRACT.md @ f54772ec92ef, vendored: its one home is there. A defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository). -->
# The adjuster contract — what both builds and both hosts agree on (the first WebAssembly spike)

**For:** the two builds of `adjust()` (Rust in `fn/rust/`, JavaScript compiled with Javy in `fn/js/`) and the two hosts that run them (`pp_wasm/pp_wasm/host.py` on the server, `hosts/host_core.mjs` in a browser or Node Worker). One text, so the four cannot drift. Written 2026-10-03.

## 1. What the function does

For each sale line, the best discount any matching rule gives, capped. A rule matches a line when:
- its `item_group` equals the line's `item_group`;
- its `customer_group` is `"*"` or equals the sale's `customer_group` (a `null` sale group matches only `"*"`);
- the line's `qty_milli` is at least the rule's `min_qty_milli`.

For one rule and one line: `discount = min(floor(line_total_minor × percent_bp / 10000), cap_minor, line_total_minor)`. A `null` cap means no cap. The product is computed exactly: in Rust as `i128`, in JavaScript as `BigInt`. It can reach 9.0 × 10¹⁹, past `i64`.

The line takes the **largest** discount among its matching rules. A tie goes to the **earliest** rule in `config.rules`. A line whose best discount is 0 gets no entry.

## 2. Input — UTF-8 JSON, built by the host

```json
{"customer_group": "MPOS Members",
 "lines": [{"luid": "L1", "item": "UN-A", "item_group": "Products", "qty_milli": 2000,
            "unit_price_minor": 3333, "line_total_minor": 6666}],
 "config": {"rules": [{"id": "R1", "item_group": "Products", "customer_group": "*",
                       "percent_bp": 1000, "cap_minor": 5000, "min_qty_milli": 0}]}}
```

**Money and quantity are integers.** Money is in minor units (cents). Quantity is in thousandths (`qty_milli`), so a weighed line needs no float. `unit_price_minor` is carried for the partner's use; this function reads only `line_total_minor`.

**The host contract** (both hosts' input builders):
- the input bytes are canonical JSON;
- every number is a non-negative integer literal with no sign, fraction or exponent — never `-0`, `1.0` or `1e3`;
- every string is well-formed Unicode, never a lone surrogate;
- no object or array is nested more than 32 deep, the partner's configuration included. Rust's `serde_json` refuses input nested beyond 128 as `input`, while JavaScript and the reference answer it.

A function is not required to agree with its twin on input outside this contract. Python's `json.dumps` and JavaScript's `JSON.stringify` both produce such input from integers and well-formed strings.

## 3. Validation — the first failure wins, in this order

| Order | Path | Rule |
|---|---|---|
| 1 | `input` | an object |
| 2 | `customer_group` | `null` or a string |
| 3 | `lines` | an array of at most 500 |
| 4 | `lines[i]` | an object |
| 5 | `lines[i].luid` | a string of 1–80 UTF-8 bytes |
| 6 | `lines[i].item` · `.item_group` | strings of at most 140 UTF-8 bytes |
| 7 | `lines[i].qty_milli` | an integer, 1 to 10¹² |
| 8 | `lines[i].unit_price_minor` · `.line_total_minor` | integers, 0 to 2⁵³−1 |
| 9 | `lines[i].luid` (again) | not equal to an earlier line's `luid` |
| 10 | `config` | an object |
| 11 | `config.rules` | an array of at most 100 |
| 12 | `config.rules[j]` | an object |
| 13 | `.id` | a string of 1–40 UTF-8 bytes |
| 14 | `.item_group` · `.customer_group` | strings of at most 140 UTF-8 bytes |
| 15 | `.percent_bp` | an integer, 0 to 10 000 |
| 16 | `.cap_minor` | `null`, or an integer from 0 to 2⁵³−1 |
| 17 | `.min_qty_milli` | an integer, 0 to 10¹² |

Each line is checked field by field in that order before the next line is read. Rules are checked the same way. A missing field fails as a wrong type. Unknown keys are ignored. A key repeated in one object keeps its last value (JSON's usual reading in both languages).

## 4. Output — exactly one of two shapes, canonical JSON, no spaces

- **Answer:** `[{"luid":"L1","discount_minor":666,"reason":"R1"}]`
  - entries in input line order, one per line with a discount above 0;
  - `reason` is the winning rule's `id`;
  - `[]` when nothing applies.
- **Refusal:** `{"error":"invalid_input","at":"lines[3].qty_milli"}`, where `at` is the first failing path in §3. A duplicate `luid` is reported at the later line's `.luid`.

**String escaping** is the shared JSON form:
- `\"`, `\\`, `\b`, `\f`, `\n`, `\r` and `\t`;
- other control characters as `\u00XX`, lower-case hexadecimal;
- everything else raw UTF-8: `/`, DEL, U+2028 and non-ASCII.

Rust's `serde_json` and JavaScript's `JSON.stringify` both write exactly this form.

## 5. The host interface — three capabilities, two ways in

| Capability | Native profile `pp` (Rust, wasm32-unknown-unknown) | Javy profile (the WASI form Javy's runtime imports) |
|---|---|---|
| read the input | `pp.read_input(ptr, len) → total` — copies up to `len` bytes and returns the full input length (call once with `len = 0` to size the buffer) | `fd_read` on fd 0; at most 16 iovecs a call |
| write the answer | `pp.write_output(ptr, len)` — appends; the whole answer is capped at 524 288 bytes, and more traps `output_too_large`. The largest answer the contract allows is about 389 000 bytes: 500 entries, each with an 80-byte luid and a 40-byte reason, every byte a control character escaped to six | `fd_write` on fd 1, same cap; at most 16 iovecs a call (`too_many_iovecs`) |
| log | `pp.log(ptr, len)` — appends, silently truncated at 1 024 bytes | `fd_write` on fd 2, same truncation |
| run | export `run() → i32`; 0 = done | export `_start`; `proc_exit(0)` = done |

**Everything else is refused or trapped, by name.** The load checks are read from the module's bytes by **one algorithm written twice** (`host_core.mjs` `shape`/`inspect`, `host.py` `shape`/`inspect`), in this order, before compiling. The spike ran both over every module and required the same verdict.
- **Refused at load**, in order:
  - `invalid_module …` — not a WebAssembly module;
  - `unsupported_type` — a type that is not a plain function type: garbage-collected structs and arrays, typed references;
  - `undeclared_import <module>.<name>` — a non-function import (memory, table, global, tag);
  - `unsupported_section <id>` — a section this host does not know;
  - `bad_signature run` · `bad_signature _start` · `missing_export run` — the entry export: `run: () -> i32` or `_start: () -> ()`;
  - `undeclared_import <module>.<name>` — any import outside the profile: a clock or random import in a native module, `env.fetch`, anything;
  - `duplicate_import <module>.<name>` · `bad_signature <module>.<name>` — each profile import at most once, with its exact signature;
  - `start_section` — no start function: nothing may run before the host has the instance;
  - `table_limit` — at most one table: a function table with a maximum of at most 10 000 entries;
  - `no_memory` — not exactly one memory of the module's own, 32-bit, unshared, exported as `memory`;
  - `no_memory_max` — no memory maximum, or one above 160 pages (10 MiB). The browser can enforce memory only through the module's own declaration, so the packager writes that maximum and both hosts check it;
  - `not_metered` — the publish manifest says the module is metered, but it carries no `pp_fuel` counter.
- **Trapped at call** (`forbidden_call <name>`): the six WASI functions Javy's runtime declares but a function never needs — `clock_time_get`, `environ_get`, `environ_sizes_get`, `fd_close`, `fd_fdstat_get`, `fd_seek`. Also `fd_read`/`fd_write` on any other fd, and a non-zero `proc_exit`.
- **Trapped at call** (`memory_out_of_bounds`): a pointer and length outside the module's memory.
- **Trapped at call** (`host_error <name>`): our own host code failed. It is named, never thrown at the caller.

**Limits:**
- **Server:** fuel 11 000 000 per call (the instruction bound Shopify publishes) → `out_of_fuel`.
- **Browser:** no fuel counter exists.
- **A metered module** (published through the fuel meter) carries its own counter, `pp_fuel`, and that counter is the bound on **both** hosts → `out_of_fuel` at the same instruction. On the server, wasmtime's fuel stays as a backstop 100 times larger. **Whether a module is metered is the publish manifest's word** (`--metered`), never the module's own exports.
- **Stack depth.** A metered module also carries an in-module stack counter that traps `integer_overflow` past 10 000 units, at the same call on every host. One shape ends sooner: a function with a large local array per call. Measured with a 4 KB array per frame, the module's own memory stack runs out first and the call traps `memory_out_of_bounds` at depth 253, below the counter, at the same depth on the server host (wasmtime 49), the browser host in Node 26 and in Chrome 152. Parity holds; the trap's reason depends on the shape. A 256-byte frame still trips the counter (`integer_overflow`, depth 1 108).
- **Both hosts: a wall-clock deadline of 1 000 ms → `timeout`.** In the browser it terminates the Worker; on the server it is wasmtime's epoch deadline, ticked every 10 ms. It is the backstop for what the counters do not price:
  - **Work done inside the host functions** — no counter prices it, so the hosts cap it themselves (the log read only as far as it is kept, at most 16 iovecs a call).
  - **A bulk `memory.fill` or `memory.copy`'s length**, which prices differently by host:
    - wasmtime 49's fuel **does** price it (measured: H10 out of fuel on the server in 5 ms);
    - **V8 has no counter at all**: H10 runs until the browser's timeout, and the killed Worker kept going for about 20 s (measured);
    - the in-module counter charges length / 64, so a metered module stops at the same unit on both hosts.

  A run ended by the clock is not deterministic, so a legitimate function must stay far inside the budget (measured in the spike).
- **Both:** a fresh instance per call. Nothing survives from one basket to the next.
