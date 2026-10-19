// run_node.mjs — the kit's BROWSER host: the browser host (client.mjs → a Worker → host_core.mjs),
// unchanged, run in Node. One module, every sample, a fresh instance per call, the 1 000 ms deadline.
//   node tools/wasm_kit/harness/run_node.mjs <module.wasm> <samples.json> [--metered]   → JSON lines on stdout
import fs from "node:fs";
import { WasmHost } from "../hosts/client.mjs";

const [, , modPath, samplesPath, ...rest] = process.argv;
const metered = rest.includes("--metered");
const samples = JSON.parse(fs.readFileSync(samplesPath)).samples;
const enc = new TextEncoder(), dec = new TextDecoder();
const h = new WasmHost({ workerUrl: new URL("../hosts/worker.mjs", import.meta.url), timeoutMs: 1000 });
await h.start();
const loaded = await h.load("m", new Uint8Array(fs.readFileSync(modPath)), metered);
if (loaded.status !== "loaded") {
  console.log(JSON.stringify({ load: loaded.status, reason: loaded.reason }));
} else {
  for (const s of samples) {
    const input = s.input_b64 !== undefined ? Uint8Array.from(Buffer.from(s.input_b64, "base64")) : enc.encode(s.input);
    const r = await h.run("m", input);
    console.log(JSON.stringify({ id: s.id, status: r.status, reason: r.reason ?? null,
                                 out: r.output ? dec.decode(r.output) : null }));
  }
}
await h.stop();
process.exit(0);
