// Source: ivendnext/partner-programme spikes/wasm/hosts/host_core.mjs @ 2799842dca46, vendored: its one home is there. A defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository).
// host_core.mjs — the BROWSER host's core (from the WebAssembly spike): runs a partner adjuster module with plain WebAssembly, inside a
// Worker (worker.mjs) in Chrome or Node. The contract is §5 of the Wasm contract (CONTRACT.md); the server twin is
// host.py and makes the same decisions with the same reason names. No fuel exists here: the wall-clock
// timeout (LIMITS.deadlineMs, the server's epoch deadline too) lives in client.mjs, which owns the Worker. Memory is
// capped by the MODULE's own declared maximum (the browser offers no other lever), checked here at load.

export const LIMITS = Object.freeze({
  maxPages: 160, outputMax: 524288, logMax: 1024, fuel: 11_000_000, deadlineMs: 1000, maxIovecs: 16, maxTable: 10000,
});
// A METERED module (tools/meter) carries its own fuel counter, the exported i64 global `pp_fuel`: set before the call,
// read after; any trap with the counter below zero is out_of_fuel — at the same instruction as on the server. WHETHER a
// module is metered is the CALLER's word (the publish manifest), never the module's own exports.

// The two profiles: every import a module may declare, with its exact signature (params -> results).
const PROFILES = {
  pp: {
    module: "pp", entry: ["run", "->i32"],
    imports: { read_input: "i32,i32->i32", write_output: "i32,i32->", log: "i32,i32->" },
  },
  javy: {
    module: "wasi_snapshot_preview1", entry: ["_start", "->"],
    imports: {
      fd_read: "i32,i32,i32,i32->i32", fd_write: "i32,i32,i32,i32->i32", proc_exit: "i32->",
      environ_get: "i32,i32->i32", environ_sizes_get: "i32,i32->i32", clock_time_get: "i32,i64,i32->i32",
      fd_close: "i32->i32", fd_fdstat_get: "i32,i32->i32", fd_seek: "i32,i64,i32,i32->i32",
    },
  },
};
const FORBIDDEN_AT_CALL = new Set(["clock_time_get", "fd_close", "fd_fdstat_get", "fd_seek"]);
const VALTYPES = { 0x7f: "i32", 0x7e: "i64", 0x7d: "f32", 0x7c: "f64", 0x7b: "v128", 0x70: "funcref", 0x6f: "externref" };

export class Refused extends Error {
  constructor(reason) {
    super(reason);
    this.reason = reason;
  }
}
class HostTrap extends Error {
  constructor(reason) {
    super(reason);
    this.reason = reason;
  }
}
class Exit extends Error {
  constructor(code) {
    super(`exit ${code}`);
    this.code = code;
  }
}

// THE SHAPE — read from the module's bytes by the same steps, in the same order, as host.py `shape`, so both hosts
// refuse the same modules with the same reason. Returns {types, imports, funcs, tables, memories, exports, start}.
export function shape(bytes) {
  const b = bytes;
  let p = 0;
  const fail = (reason) => { throw new Refused(reason); };
  const u8 = () => { if (p >= b.length) fail("invalid_module truncated"); return b[p++]; };
  const leb = () => { let r = 0, sh = 0, x; do { x = u8(); r += (x & 0x7f) * 2 ** sh; sh += 7; } while (x & 0x80); return r; };
  const name = () => { const n = leb(); const s = new TextDecoder().decode(b.subarray(p, p + n)); p += n; return s; };
  const valtype = () => VALTYPES[u8()] ?? fail("unsupported_type");
  const limits = () => { const f = u8(); const min = leb(); const max = f & 1 ? leb() : null; return { flags: f, min, max }; };
  if (b.length < 8 || b[0] !== 0 || b[1] !== 0x61 || b[2] !== 0x73 || b[3] !== 0x6d || b[4] !== 1) fail("invalid_module header");
  p = 8;
  const m = { types: [], imports: [], funcs: [], tables: [], memories: [], exports: [], start: false };
  while (p < b.length) {
    const id = u8();
    const size = leb();
    const end = p + size;
    if (id === 1) {
      for (let n = leb(); n > 0; n--) {
        if (u8() !== 0x60) fail("unsupported_type");
        const params = []; for (let k = leb(); k > 0; k--) params.push(valtype());
        const results = []; for (let k = leb(); k > 0; k--) results.push(valtype());
        m.types.push(`${params.join(",")}->${results.join(",")}`);
      }
    } else if (id === 2) {
      for (let n = leb(); n > 0; n--) {
        const imp = { module: name(), name: name(), kind: u8() };
        if (imp.kind === 0) imp.type = leb();
        else if (imp.kind === 1) { u8(); limits(); }
        else if (imp.kind === 2) limits();
        else if (imp.kind === 3) { valtype(); u8(); }
        else fail(`undeclared_import ${imp.module}.${imp.name}`);
        m.imports.push(imp);
      }
    } else if (id === 3) {
      for (let n = leb(); n > 0; n--) m.funcs.push(leb());
    } else if (id === 4) {
      for (let n = leb(); n > 0; n--) { const t = u8(); m.tables.push({ ref: t, ...limits() }); }
    } else if (id === 5) {
      for (let n = leb(); n > 0; n--) m.memories.push(limits());
    } else if (id === 7) {
      for (let n = leb(); n > 0; n--) m.exports.push({ name: name(), kind: u8(), index: leb() });
    } else if (id === 8) {
      m.start = true;
    } else if (id !== 0 && id !== 6 && id !== 9 && id !== 10 && id !== 11 && id !== 12) {
      fail(`unsupported_section ${id}`);
    }
    p = end;
  }
  return m;
}

// Load-time checks (CONTRACT §5), in this order: the profile from the entry export · every import inside the profile,
// once, with its exact signature · no start section · at most one bounded funcref table · exactly one 32-bit, unshared
// memory of the module's own, exported, with a maximum of at most 160 pages · a metered module's counter.
export function inspect(bytes, metered = false) {
  const m = shape(bytes);
  const funcType = (i) => {
    const imported = m.imports.filter((x) => x.kind === 0);
    return m.types[i < imported.length ? imported[i].type : m.funcs[i - imported.length]];
  };
  const exp = (n) => m.exports.find((e) => e.name === n);
  let profile = null;
  for (const [key, pr] of Object.entries(PROFILES)) {
    const e = exp(pr.entry[0]);
    if (e && e.kind === 0) {
      if (funcType(e.index) !== pr.entry[1]) throw new Refused(`bad_signature ${pr.entry[0]}`);
      profile = key;
      break;
    }
  }
  if (!profile) throw new Refused("missing_export run");
  const pr = PROFILES[profile];
  const seen = new Set();
  for (const imp of m.imports) {
    const id = `${imp.module}.${imp.name}`;
    if (imp.kind !== 0 || imp.module !== pr.module || !(imp.name in pr.imports)) throw new Refused(`undeclared_import ${id}`);
    if (seen.has(id)) throw new Refused(`duplicate_import ${id}`);
    seen.add(id);
    if (m.types[imp.type] !== pr.imports[imp.name]) throw new Refused(`bad_signature ${id}`);
  }
  if (m.start) throw new Refused("start_section");
  if (m.tables.length > 1 || m.tables.some((t) => t.ref !== 0x70 || t.flags !== 1 || t.max > LIMITS.maxTable)) {
    throw new Refused("table_limit");
  }
  const mem = m.memories[0];
  const memExport = exp("memory");
  if (m.memories.length !== 1 || (mem.flags & ~1) || !memExport || memExport.kind !== 2 || memExport.index !== 0) {
    throw new Refused("no_memory");
  }
  if (mem.max === null || mem.max > LIMITS.maxPages || mem.min > LIMITS.maxPages) throw new Refused("no_memory_max");
  if (metered) {
    const g = exp("pp_fuel");
    if (!g || g.kind !== 3) throw new Refused("not_metered");
  }
  return profile;
}

function view(st, ptr, len) {
  if (!st.mem) throw new HostTrap("call_during_start"); // a start section calling in before the instance exists
  ptr >>>= 0;
  len >>>= 0;
  if (ptr + len > st.mem.buffer.byteLength) throw new HostTrap("memory_out_of_bounds");
  return new Uint8Array(st.mem.buffer, ptr, len);
}

function emit(st, which, chunk) {
  if (which === "out") {
    if (st.outLen + chunk.length > LIMITS.outputMax) throw new HostTrap("output_too_large");
    st.out.push(chunk.slice());
    st.outLen += chunk.length;
  } else if (st.logLen < LIMITS.logMax) {
    const keep = chunk.subarray(0, LIMITS.logMax - st.logLen);
    st.log.push(keep.slice());
    st.logLen += keep.length;
  }
}

function ppImports(st) {
  return {
    pp: {
      read_input(ptr, len) {
        const dst = view(st, ptr, len);
        dst.set(st.input.subarray(0, Math.min(dst.length, st.input.length)));
        return st.input.length;
      },
      write_output(ptr, len) { emit(st, "out", view(st, ptr, len)); },
      log(ptr, len) { emit(st, "log", view(st, ptr, len)); },
    },
  };
}

function u32(st, ptr) {
  return new DataView(view(st, ptr, 4).slice().buffer).getUint32(0, true);
}
function setU32(st, ptr, v) {
  const at = view(st, ptr, 4).byteOffset; // the bounds check first, then the write
  new DataView(st.mem.buffer).setUint32(at, v, true);
}

function javyImports(st) {
  const wasi = {
    fd_read(fd, iovs, n, nread) {
      if (fd !== 0) throw new HostTrap(`forbidden_call fd_read(${fd})`);
      if (n >>> 0 > LIMITS.maxIovecs) throw new HostTrap("too_many_iovecs");
      let total = 0;
      for (let i = 0; i < n; i++) {
        const dst = view(st, u32(st, iovs + 8 * i), u32(st, iovs + 8 * i + 4));
        const k = Math.min(dst.length, st.input.length - st.inPos);
        dst.set(st.input.subarray(st.inPos, st.inPos + k));
        st.inPos += k;
        total += k;
      }
      setU32(st, nread, total);
      return 0;
    },
    fd_write(fd, iovs, n, nwritten) {
      if (fd !== 1 && fd !== 2) throw new HostTrap(`forbidden_call fd_write(${fd})`);
      if (n >>> 0 > LIMITS.maxIovecs) throw new HostTrap("too_many_iovecs");
      let total = 0;
      for (let i = 0; i < n; i++) {
        const src = view(st, u32(st, iovs + 8 * i), u32(st, iovs + 8 * i + 4));
        emit(st, fd === 1 ? "out" : "log", src);
        total += src.length;
      }
      setU32(st, nwritten, total);
      return 0;
    },
    proc_exit(code) { throw new Exit(code); },
    // an EMPTY environment, answered as a constant: Javy's runtime asks for it on its JSON.parse error path (measured)
    environ_sizes_get(countPtr, sizePtr) { setU32(st, countPtr, 0); setU32(st, sizePtr, 0); return 0; },
    environ_get() { return 0; },
  };
  for (const name of FORBIDDEN_AT_CALL) {
    wasi[name] = () => { throw new HostTrap(`forbidden_call ${name}`); };
  }
  return { wasi_snapshot_preview1: wasi };
}

// The engine's own trap text, named the way wasmtime names its trap codes (host.py `_TRAP_NAMES`).
function trapName(e) {
  const m = String(e && e.message);
  if (e instanceof RangeError && /call stack/i.test(m)) return "stack_overflow";
  if (/unreachable/.test(m)) return "unreachable";
  if (/memory access out of bounds/.test(m)) return "memory_out_of_bounds";
  if (/divide by zero|remainder by zero/.test(m)) return "integer_division_by_zero";
  if (/divide result unrepresentable|integer overflow/.test(m)) return "integer_overflow";
  if (/float unrepresentable|integer result unrepresentable/.test(m)) return "bad_conversion_to_integer";
  if (/out of memory|could not allocate/i.test(m)) return "out_of_memory";
  return `trap ${m.slice(0, 120)}`;
}

const now = () => performance.now();

// One call: a FRESH instance, the input, the answer. Never throws: every end is a status with a named reason.
export function runOnce(module, profile, input, metered = false) {
  const st = { input, inPos: 0, out: [], outLen: 0, log: [], logLen: 0, mem: null, meter: null };
  const t0 = now();
  let t1 = t0, status = "ok", reason = null;
  try {
    const inst = new WebAssembly.Instance(module, profile === "pp" ? ppImports(st) : javyImports(st));
    t1 = now();
    st.mem = inst.exports.memory;
    if (metered) {
      st.meter = inst.exports.pp_fuel;
      st.meter.value = BigInt(LIMITS.fuel);
    }
    if (profile === "pp") {
      const rc = inst.exports.run();
      if (rc !== 0) [status, reason] = ["trap", `nonzero_exit ${rc}`];
    } else {
      inst.exports._start();
    }
  } catch (e) {
    if (t1 === t0) t1 = now();
    if (e instanceof Exit) {
      if (e.code !== 0) [status, reason] = ["trap", `forbidden_call proc_exit(${e.code})`];
    } else if (e instanceof HostTrap) {
      [status, reason] = ["trap", e.reason];
    } else if (e instanceof WebAssembly.RuntimeError || e instanceof WebAssembly.LinkError || e instanceof RangeError) {
      [status, reason] = ["trap", trapName(e)];
    } else {
      [status, reason] = ["trap", `host_error ${e && e.name}`]; // our own code failed: named, never thrown on
    }
  }
  const t2 = now();
  let meterUsed = null;
  if (st.meter) {
    const left = st.meter.value;
    meterUsed = LIMITS.fuel - Number(left);
    if (status === "trap" && left < 0n) reason = "out_of_fuel";
  }
  const join = (parts, len) => {
    const all = new Uint8Array(len);
    let off = 0;
    for (const p of parts) { all.set(p, off); off += p.length; }
    return all;
  };
  return {
    status, reason,
    output: status === "ok" ? join(st.out, st.outLen) : null,
    log: new TextDecoder().decode(join(st.log, st.logLen)),
    instantiate_ms: t1 - t0, run_ms: t2 - t1, meter_used: meterUsed,
    memory_bytes: st.mem ? st.mem.buffer.byteLength : null,
  };
}

// The shape first (from the bytes, as the server does), then compile: {module, profile, metered} or a Refused.
export async function load(bytes, metered = false) {
  const profile = inspect(bytes, metered);
  let module;
  try {
    module = await WebAssembly.compile(bytes);
  } catch (e) {
    throw new Refused(`invalid_module ${String(e.message).slice(0, 80)}`);
  }
  return { module, profile, metered };
}
