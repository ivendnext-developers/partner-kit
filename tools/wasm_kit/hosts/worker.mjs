// Source: ivendnext/partner-programme spikes/wasm/hosts/worker.mjs @ 2799842dca46, vendored: its one home is there. A defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository).
// worker.mjs — the Worker side of the browser host (from the WebAssembly spike). Holds compiled modules by key and runs one call per
// message with host_core.runOnce. Runs unchanged as a browser module Worker or a Node worker_threads Worker.
// The timeout is NOT here: a busy Worker cannot time itself out, so client.mjs terminates it from outside.
import { load, runOnce, Refused } from "./host_core.mjs";

const isNode = typeof process !== "undefined" && !!(process.versions && process.versions.node);
const port = isNode ? (await import("node:worker_threads")).parentPort : self;
const send = (m) => port.postMessage(m);
const modules = new Map();

async function handle(msg) {
  if (msg.op === "load") {
    const t0 = performance.now();
    try {
      const m = await load(new Uint8Array(msg.bytes), !!msg.metered);
      modules.set(msg.key, m);
      send({ id: msg.id, status: "loaded", profile: m.profile, compile_ms: performance.now() - t0 });
    } catch (e) {
      send({ id: msg.id, status: "refused", reason: e instanceof Refused ? e.reason : `load_failed ${e.message}` });
    }
  } else if (msg.op === "run") {
    const m = modules.get(msg.key);
    if (!m) return send({ id: msg.id, status: "refused", reason: "not_loaded" });
    send({ id: msg.id, ...runOnce(m.module, m.profile, new Uint8Array(msg.input), m.metered) });
  }
}

if (isNode) port.on("message", handle);
else port.onmessage = (ev) => handle(ev.data);
