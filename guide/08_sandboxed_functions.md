# 8. Sandboxed functions

**For:** a builder whose logic must run inside a sale and give the same answer on the server and on an offline till.
**Reference implementation:** [the kit's README](../tools/wasm_kit/README.md) and [contract](../tools/wasm_kit/CONTRACT.md) (the commands below are the README's) · the first measurements are summarised in the repository's [README](../README.md#the-webassembly-verdict).

A sandboxed function is a small program you write in Rust and compile to WebAssembly. The shop runs the same file on its server and on the till, so a decision gives the same answer online and offline. This chapter shows how to build one and check it yourself with the kit.

> **Package or module?** A **package** is your whole app: its records, fields, print formats, buttons, services and label layouts, sent as one manifest. The shop's administrator pastes your file, reads *What it will do*, consents and installs it; later the shop can update it or remove it, and *Connected apps* lists every one. A **module** is one small program (the sandboxed function this chapter builds) that does one job at an extension point, such as adjusting a price or checking a sale before payment. **Two extension points take a module today: the check before payment and pricing.** The shop's administrator adds your file in Desk, with a certificate our review team signs, and can withdraw it; a package cannot carry one yet. **In short:** a package is the app, and a module is one program that does one job.
>
> *Technical note:* a package installs from the **Retail Extension Package** screen in Desk; a module is a **Retail Extension Module** record that the shop's administrator adds in Desk, at an extension point that takes one (see *Read this first*, below).

## Read this first

- **Two extension points take a module, and only a module we have certified runs.** The check before payment and pricing take one; capture, save rules and every other extension point have no module leg. We sign a module's sha256 for one extension point and one version, by hand, after running this chapter's checks on it ourselves. The route for submitting one to us, and the automatic intake behind it, are planned, not built (chapter 17). A shop runs a module we have certified once its administrator adds it in Desk; a shop that adds none runs none.
- **A certificate is not tied to one shop.** A shop's administrator can withdraw a module on that shop (its record is kept; it stops running). We cannot withdraw one certificate from every shop at once. A product release that changes the certificate key stops the shop's server running every module signed with the old one, but a till keeps running a module it already holds, offline, until the shop's administrator withdraws that module.
- **The template has run on the product's own host.** It is the product's own pricing test module: built through the kit's meters it is byte-identical to it. On our test bench (2026-10-12) the product's host admitted it under our certificate and it took a member discount off a line on the phone, counter and tablet screens, online and offline. No module a partner built has run on a shop yet.
- **A pricing function can only take money off a line, up to the shop's own limit.** Pricing takes money off a line after every promotion, never more than that limit, which starts at 0 (at 0 the module is not even run) until the shop raises it. A line a Pricing Rule has already priced, a return, a zero-rate line and a gift-card line are never offered to it. A function cannot raise a price, and the Desk POS does not run the pricing module: a sale rung there is priced without it. **On an exchange,** a shop that keeps the price paid gives a replacement line the returned item's own discount; a replacement line your module has priced keeps your price, and the returned discount is not carried onto it.

## When to use it

Rung 5 of the ladder (chapter 3), the last before asking for an extension point (chapter 9): only when a decision must be **computed by your own logic** and must also work on a till with no network. Try configuration (chapter 4) and a till key (chapter 6) first. **Write it in Rust**, the language measured. A function that only ever runs on the server may also be compiled from JavaScript (see *What is refused*).

## Steps

1. **Install what the kit needs.**
   - Rust, installed with rustup at its default place (the kit looks for `~/.cargo/bin/cargo`), with the `wasm32-unknown-unknown` target.
   - Node 22 or later.
   - Python 3.10 or later with the one library the README names, `wasmtime==49.0.0`.

   Then build the two meters once, each with `cargo build --release`: the fuel meter in `tools/wasm_kit/meter` and the stack meter in `tools/wasm_kit/stackmeter`. The kit looks for them at those paths, and publishing fails without them. Run every command from the repository's root. (The two test hosts the kit uses are in `tools/wasm_kit/vendor/` and `tools/wasm_kit/hosts/`.)
2. **Copy the template and write your function.** Edit one file only, `src/point.rs`. It ships with a discount adjuster as the worked example.

   ```bash
   cp -r tools/wasm_kit/template my_point
   ```

3. **Write to the contract.**
   - **One message in, one answer out,** both UTF-8 JSON.
   - **Numbers are whole numbers.** Money is in integer minor units, quantity in integer thousandths (`qty_milli`). No fractions, signs or exponents in numbers; nesting at most 32.
   - **Check the input in the published order.** On the first bad field, answer `{"error":"invalid_input","at":"<first failing path>"}`.
   - **The function sees only what the host gives it:** `pp.read_input`, `pp.write_output`, `pp.log`, an exported `run()` and its memory. A clock, randomness, the network or a start function is refused when the module loads.
   - **Limits:** fuel 11 000 000 units; memory 10 MiB; an answer at most 512 KiB; the log 1 KiB; a fresh instance on every call.
   - **Keep the template's own JSON code.** It uses whole numbers only, on purpose; a common JSON library brings in floating-point instructions, which a till function may not have.
4. **Build.** This runs your Rust tests first. Give the folder of your crate, relative or absolute.

   ```bash
   python3 tools/wasm_kit/kit.py build my_point
   ```

   The raw module lands in `my_point/target/wasm32-unknown-unknown/release/`, named after your crate.
5. **Publish.** Scan, stack meter, fuel meter, memory cap, size cap and load checks, in that order; it writes a `*.publish.json` with the size, sha256 and bounds.

   ```bash
   python3 tools/wasm_kit/kit.py publish <raw.wasm> <out.wasm>
   ```

   A till function may have **no floating-point instruction, no SIMD, no atomics**, keeps recursion shallow (the stack bound is 10 000 units, written into the module), and is at most **256 KB** once metered. A function that never runs on a till has a shorter path, in step 7.
6. **Prove the same answer on both hosts,** on samples of your own in the shape of the template's `samples/samples.json` (an input and the expected answer; `must_answer` marks the realistic ones, the rest must at least agree). A stress basket may run out of fuel, but it must do so identically on both hosts:

   ```bash
   python3 tools/wasm_kit/kit.py parity <out.wasm> my_point/samples/samples.json --metered
   ```

7. **Run the local admission.** It takes your **raw** build, publishes it itself and runs every sample on both hosts. A trap on a realistic sample, a split between the hosts or a wrong answer is a refusal, named. A module that already carries a meter is refused, because a module's own counter is never trusted:

   ```bash
   python3 tools/wasm_kit/kit.py admit <raw.wasm> my_point/samples/samples.json
   ```

   **A function that never runs on a till** skips steps 5 and 6 and runs the same command with `--server-only` added. The module is then checked as given, with no size cap, and run on the server host only: no browser host, no parity, no kit meter (the server host's own fuel limit still applies), and the kit's own check allows floats and SIMD, atomics never. The product's host is stricter: it allows floats and SIMD only in a server-only module whose extension point touches no price or decision, and by default every extension point does. Today both extension points that take a module, the check and pricing, run it on the till, so the product refuses a server-only module at either: a `--server-only` build has nowhere to run yet.

   This is the check you run yourself. It does not certify your module: we sign a module's sha256 ourselves, by hand, after running the same harness on it. What we run on a submission, and the route for submitting one, are not covered by the kit yet (chapter 17).

## What is refused, and why

- **Anything the module asks for beyond the three host functions** (a clock, randomness, the network): refused at load, named, so the same input gives the same answer everywhere. Likewise a missing memory maximum or one above 10 MiB, and an unusual shape such as a start function.
- **A floating-point, SIMD or atomic instruction in a till function,** because a float's result can differ by host.
- **A module that already carries a meter.**
- **A run past its fuel, a pointer outside the module's memory, an answer over 512 KiB:** a trap at the call, named, never half an answer.
- **JavaScript on the till.** On the till it is Rust only: a JavaScript function started too slowly on our slow till stand-in. A **server-only** function in JavaScript is admitted, with no size cap. How to build that JavaScript module is not in the kit's README.

## When your service is down, and when the till is offline

- **There is no service.** The function runs inside the shop and inside the till; nothing calls you.
- **Offline,** the till runs the same bytes from its offline copy of the module. That was walked on our test bench's three till screens (2026-10-12); a real low-end Android till's timing is still owed.
- **A refusal, a trap or an over-budget run means no adjustment (pricing) or your declared down answer (the check), never half of one.**

## Technical notes

### What the kit has proven

- **The template** (35 707 bytes raw, 78 688 published, no float, SIMD or atomic instruction): **192 of 192** samples identical on the server host and the browser host. The 181 it answered all equal the reference answers; the 11 oversized stress baskets stopped for fuel on both hosts alike. Admitted.
- **Twenty-five hostile modules** were all refused by the local admission, as a till function and as a server-only one, each with a named reason.
- **The stack bound:** a deliberately recursive module, run through the kit's meters, answered at depth 1 000 and trapped from 1 500 **on both hosts alike**.
- **Speed on a slow till stand-in** (the earlier spike, a browser slowed six times): a Rust function started in 11.7 ms plain and 21.3 ms metered, against 50 ms.
- The kit's own tests, 5 of 5.

### What it has not

- **Against the product, beyond one module.** The product's host has run the template's module, which we certified. A module a partner built has not run on a shop.
- **Chrome and a real till through the kit.** The kit's browser host runs in Node; the earlier spike ran Chrome. **A real low-end Android till's timing is still owed.**
- **The stack bound for any function shape but that one:** it counts frames and ignores deeper operand stacks and spills.
- **A function changing a price for a real shop:** the template's module took money off a line on our test bench only.
- **JavaScript on the server beyond the samples.** Languages other than Rust and JavaScript were not measured.
- **The offline copy** carrying a partner's module on a real low-end till, and any intake check of a submission.

### Why it is built this way

- **The template's integer-only JSON.** The template carries its own integer-only JSON on purpose: a common JSON library put 26 floating-point instructions into the earlier spike's function.
- **The size cap on `publish`.** `publish --server-only` applies no size cap, as `admit --server-only` does; until 2026-10-07 it still applied the till's 256 KB cap (fixed with a test). A function that runs on a till keeps the cap.
- **JavaScript on the till.** JavaScript compiled with Javy gave identical answers but took 68.8 ms to start in a browser slowed six times, our till stand-in, against a 50 ms budget. The older recipe says JavaScript is "not offered today". The kit's README, later, says a **server-only** function in JavaScript is admitted with no size cap: the Javy build was admitted through `admit --server-only`, and five hostile JavaScript modules were still refused.
- **Offline.** In the first spike the same answers came back from a browser with its network switched off; no till did it.

## See also

[3. The ladder and the four rules](03_ladder_and_never_list.md) · [6. Till keys](06_till_keys.md) · [9. The extension-point catalogue and requests](09_points_and_requests.md) · [14. Testing and release](14_testing_and_release.md) · [17. Submitting, support, feedback](17_submit_support_feedback.md)
