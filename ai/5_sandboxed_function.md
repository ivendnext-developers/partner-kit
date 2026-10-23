# A sandboxed function: logic that runs inside a sale (way in 5)

**Goal.** A small function, compiled to WebAssembly, that gives the same answer on the server and on an offline till, at an extension point that offers one.

**Read first, and tell the person.** [guide/08_sandboxed_functions.md](../guide/08_sandboxed_functions.md) says which extension points take a sandboxed function today: the check before payment and pricing. If the need is at another, a module has nowhere to go: say so, use a higher way in, or request the extension point (guide 9, `feedback/point_request.md`). Tell the person too that a module runs on a retailer's iVendNext only after CitiXsys certifies it (by hand today; a route for submitting one is planned) and the retailer's administrator adds it in Desk. Do not build the function and hope.

**Read.** [tools/wasm_kit/README.md](../tools/wasm_kit/README.md) · [tools/wasm_kit/CONTRACT.md](../tools/wasm_kit/CONTRACT.md) · [tools/wasm_kit/HOST_CONTRACT.md](../tools/wasm_kit/HOST_CONTRACT.md).

**Template to copy.** [tools/wasm_kit/template/](../tools/wasm_kit/template/) — you edit one file, `src/point.rs`; its `samples/samples.json` (inside the template) holds the cases.

**Steps.**
1. Install what the kit needs (README: Rust with the `wasm32-unknown-unknown` target, Node 22 or later, Python with `wasmtime==49.0.0`), then build the two meters once, each with `cargo build --release`, in `tools/wasm_kit/meter` and `tools/wasm_kit/stackmeter`. Installing a toolchain is the person's call: ask first. The `python` in the commands below is the Python environment that has `wasmtime`, not the system's `python3`.
2. `cp -r tools/wasm_kit/template my_point`, then write your function in `src/point.rs` to the contract: whole numbers only (money in integer minor units, quantity in thousandths), the input checked in the published order, only the host's functions. Keep the template's own JSON code; a common JSON library brings in floating point, which a till function may not use.
3. Write sample cases with the answers you expect, in `samples.json`.
4. Build and test: `python tools/wasm_kit/kit.py build my_point`. Then `kit.py admit <raw.wasm> my_point/samples/samples.json` (add `--server-only` for a function that never runs on a till).

**Check.** `python3 tools/check/check.py <project folder>` checks each `.wasm` starts like a module and scans it for SIMD, atomics, unknown instructions and, unless you pass `--server-only`, floating point in its instructions and local types. That is only the first of the kit's checks: `kit.py admit` is the one that runs every sample on both hosts and must pass. Our own certificate is a separate step the kit cannot give; never claim it.

**Done looks like.** `check.py` is green on the folder; `kit.py admit` passes with the module published by the kit's own steps; every sample answer matches; the person knows which extension point it targets and that CitiXsys signs it, not you.

**Never.** Use a clock, randomness, the network or a start function; call out of the sandbox; change a price after the cashier has seen it. For logic that does not need to run inside the sale, use way 2 or 3.
