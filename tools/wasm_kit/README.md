# The Wasm kit — write, test and publish a sandboxed function

An extension point can offer a **sandboxed function**: a small piece of logic, written in Rust and compiled to WebAssembly, that runs inside a sale. Two extension points are built for one in the POS app — the price module (P-PRICE) and the check's module leg (P-CHECK) — and each runs one only after CitiXsys has certified it and the retailer's administrator has added it in Desk. This kit builds your function, checks it and runs it on your own machine, on a server host and on a browser host; a real browser and a real low-end till are not run by the kit.

**When to use it:** the extension point you build for offers a sandboxed function. Outsiders never write Python inside a customer's site; logic that must run inside a sale goes in a **sandboxed function** (and data in a **manifest**).

**The contracts:** [`CONTRACT.md`](CONTRACT.md) (per extension point) and [`HOST_CONTRACT.md`](HOST_CONTRACT.md) (the two hosts).

## What you need

Rust with the `wasm32-unknown-unknown` target; Node 22+; Python 3.10+ with `wasmtime==49.0.0`. Build the two meters once, each with `cargo build --release`: the fuel meter in `meter/` and the stack meter in `stackmeter/`.

The kit runs your function on two hosts: the server host `vendor/host.py` and the browser host `hosts/` (run in Node here — the same code a till runs in a browser).

## The five steps

| Step | Command (from the repository's root, in a Python environment with `wasmtime==49.0.0`) | What it checks |
|---|---|---|
| 1. Copy the template, write your function in `src/point.rs` (the only file you edit) | `cp -r tools/wasm_kit/template my_point` | — |
| 2. Build (runs your Rust tests first) | `python tools/wasm_kit/kit.py build my_point` | it compiles to `wasm32-unknown-unknown` |
| 3. Publish (a function that runs on the till): scan → stack meter → fuel meter → memory cap → size cap → load checks | `… kit.py publish <raw.wasm> <out.wasm>` | the module is shaped as the hosts require; a `*.publish.json` records its size, sha256 and bounds |
| 4. Parity on your samples, on the server host and the browser host | `… kit.py parity <out.wasm> my_point/samples/samples.json --metered` | identical result on both hosts for every sample; every answer equals the expected one |
| 5. The local admission (the check we plan to run on a submission) | `… kit.py admit <raw.wasm> my_point/samples/samples.json` (add `--server-only` for a function that never runs on a till: no size cap, server host only) | it takes your **raw** build, publishes it itself, then runs every sample on both hosts |

## What is refused, and why

- **The kit does not certify.** A partner never vouches for its own module. **We** run this same harness on a submitted module and sign its sha256 with our module certificate key (built; by hand until the submission route and its automatic intake exist — guide chapter 8, step 7; chapter 17). The POS app accepts a module certified with that key, which is pinned in it; the retailer's administrator adds the module in Desk.
- **A module that already carries a meter is refused** at admission: a module's own counter is never trusted. Submit your raw build.
- **Any trap, refusal or wrong answer** on any sample, on either host, is a refusal, named.
- **Floats, SIMD and atomics.** A function that runs on the till may not use floating-point or SIMD instructions, because a float's result can differ between the two hosts; no function may use atomics ([`CONTRACT.md`](CONTRACT.md)). The scan reads every instruction for floats, SIMD, atomics and anything unknown. The template's JSON is integer-only for this reason. If your JSON library brings floats, move to the template's JSON or publish as server-only.
- **JavaScript** (compiled with Javy) is allowed for a server-only function, with no size cap. On the till it stays stopped: too slow to cold-start, and floats/SIMD.

## What is where

| Path | What |
|---|---|
| `CONTRACT.md` | the per-extension-point contract and what the kit adds to the host contract |
| `HOST_CONTRACT.md` | the host contract both hosts keep: input and output, validation, escaping, the host interface, the limits |
| `template/` | the Rust template: `src/lib.rs` (host glue), `src/json.rs` (integer-only JSON — no float instruction), `src/point.rs` (**yours**; ships with a `price/1` member discount, taken after the promotions, as the worked example), `samples/samples.json` (196 parity samples in the `price/1` shape, with expected answers) |
| `scan.py` | reads every instruction: floats, SIMD, atomics, anything unknown |
| `tests/` | the scan's laptop tests, on modules built byte by byte (no Rust, no Node): `python3 -m unittest discover -s tools/wasm_kit/tests` |
| `stackmeter/` | the deterministic stack bound, written into the module |
| `meter/` | the fuel meter, written into the module |
| `kit.py` | build · publish · parity · admit |
| `vendor/` · `hosts/` | the server host and the publish packager; the browser host |
| `harness/run_node.mjs` | the browser host in Node |

## Technical notes

### The two hosts

The two hosts are the ones the first spike proved, unchanged: the server host `vendor/host.py` (wasmtime, fuel) and the browser host `hosts/` (a Worker; run in Node here, the same code a till runs in a browser).

### Step 5 in full

`admit` takes your **raw** build (a module that already carries a meter is refused — a module's own counter is never trusted), publishes it itself, then runs every sample on both hosts; any trap, refusal or wrong answer is a refusal, named.

### Measured (2026-10-04, on our laptop)

- **The template (2026-10-12, the `price/1` member discount):** 36 303 bytes raw, **79 473 published** (both meters), 0 float / SIMD / atomic instructions, sha256 `2950a196a8e17f88334ba2527ed5f49d1e273f80e415d816b78ad8584357372f` — the same bytes as the POS app's own test module `price_member.wasm`. Parity: **196 of 196** samples identical on both hosts; the 185 answered all equal the expected answers; the 11 oversized stress baskets stop `out_of_fuel` on both hosts alike. Admitted. (Measured 2026-10-04 on the earlier adjuster: 192 of 192.)
- **25 hostile modules:** all refused by the local admission, as a till function and as a server-only function, each with a named reason.
- **The stack bound:** a deliberately recursive module through the kit's meters answers at depth 1 000 and traps `integer_overflow` from 1 500 — **on both hosts alike**, where without the counter the two hosts split at 8 000. It holds while the counter trips before an engine's own stack; that is measured for this one function shape only (`CONTRACT.md` §2).
- **JavaScript (compiled with Javy) for a server-only function — allowed, no size cap.** The static Javy build (1 361 983 bytes) is **admitted** as a server-only function (every must-answer sample correct on the server host), and five hostile JavaScript modules are all still refused on that path (`out_of_fuel` ×3, `forbidden_call clock_time_get` ×2). On the till, JavaScript stays stopped: too slow to cold-start, and floats/SIMD. The repository's README summarises the measurements behind rung 5.

### Bounds

- The browser host here is Node running the browser host's code; a real browser and a real low-end till are not run by the kit.
- A static call graph would call ordinary Rust recursive (indirect calls through its formatting code — measured), so the stack bound is the in-module counter, never a graph.
- A partner using a JSON library that brings floats must move to the template's JSON or publish as server-only.
- **Submission: planned, not built; signing: built, by hand.** No route for submitting a module exists yet (guide chapter 17, *Submit*). We sign a module's sha256 with our module certificate key after running this harness on it ourselves; the POS app accepts it under that key, which is pinned in it. Only the local admission above is built and measured.
