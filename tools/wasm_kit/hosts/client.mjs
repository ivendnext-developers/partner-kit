// Source: ivendnext/partner-programme spikes/wasm/hosts/client.mjs @ 2799842dca46, vendored: its one home is there. A defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository).
// client.mjs — the page side of the browser host (from the WebAssembly spike). Owns ONE Worker; a call that does not answer within
// `timeoutMs` ends with {status: "trap", reason: "timeout"} — the Worker is terminated (the only way to stop a
// running module in a browser) and a fresh one is started, with every loaded module loaded again. Runs in Chrome
// (a module Worker) and in Node (worker_threads), so the harness and the till test page share every line.
const isNode = typeof process !== "undefined" && !!(process.versions && process.versions.node);

export class WasmHost {
  constructor({ workerUrl, timeoutMs }) {
    this.workerUrl = workerUrl;
    this.timeoutMs = timeoutMs;
    this.loaded = new Map(); // key -> {bytes, metered}, to reload after a timeout
    this.pending = new Map();
    this.seq = 0;
  }

  async start() {
    if (isNode) {
      const { Worker } = await import("node:worker_threads");
      this.worker = new Worker(this.workerUrl);
      this.worker.on("message", (m) => this._answer(m));
    } else {
      this.worker = new Worker(this.workerUrl, { type: "module" });
      this.worker.onmessage = (ev) => this._answer(ev.data);
    }
  }

  _answer(m) {
    const p = this.pending.get(m.id);
    if (!p) return;
    clearTimeout(p.timer);
    this.pending.delete(m.id);
    p.resolve(m);
  }

  async _ask(msg, transferable) {
    if (this.ready && msg.op === "run") await this.ready;   // a replacement Worker after a timeout: wait for its load
    const id = ++this.seq;
    return new Promise((resolve) => {
      const timer = setTimeout(async () => {
        this.pending.delete(id);
        // answer the caller AT the deadline, then replace the Worker. ⚠ Measured (Node 26): terminating a Worker busy
        // in a loop of bulk memory.fill took ~20 s (a plain loop: 2 ms) — so the old Worker is killed in the
        // background and never awaited; the call already has its answer (a metered module stops itself instead).
        resolve({ id, status: "trap", reason: "timeout" });
        const old = this.worker;
        old.unref?.();   // Node: a dying Worker must not hold the process open (the browser has no such call)
        old.terminate();
        this.ready = (async () => {
          await this.start();
          for (const [key, l] of this.loaded) await this._ask({ op: "load", key, bytes: l.bytes.slice(), metered: l.metered });
        })();
      }, this.timeoutMs);
      this.pending.set(id, { resolve, timer });
      this.worker.postMessage({ ...msg, id }, transferable || []);
    });
  }

  // `metered` is the publish manifest's word for this module, never the module's own (CONTRACT §5)
  async load(key, bytes, metered = false) {
    const answer = await this._ask({ op: "load", key, bytes: bytes.slice(), metered });
    if (answer.status === "loaded") this.loaded.set(key, { bytes: bytes.slice(), metered });
    return answer;
  }

  run(key, inputBytes) {
    return this._ask({ op: "run", key, input: inputBytes.slice() });
  }

  async stop() {
    if (this.ready) await this.ready;   // a replacement Worker still starting is the one to stop, not the dying one
    await this.worker.terminate();
  }
}
