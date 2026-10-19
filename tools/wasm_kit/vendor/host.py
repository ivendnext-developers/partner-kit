# Source: ivendnext/partner-programme spikes/wasm/pp_wasm/pp_wasm/host.py @ 2799842dca46, vendored: its one home is there. A defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository).
"""host.py — the SERVER host (from the WebAssembly spike): runs a partner adjuster module with wasmtime-py, fuel on, a fresh instance per
call. The contract is §5 of the Wasm contract (CONTRACT.md); the browser twin is host_core.mjs and makes the
same decisions with the same reason names. Imports nothing from the framework, so the scratch harness
(harness/run_server.py) and the till key (key.py) run exactly this file.

Pinned: wasmtime==49.0.0 (pyproject). Its API changes with every monthly major version (STRESS_TEST [S13]).
"""
from __future__ import annotations

import threading
import time

import wasmtime

LIMITS = {"max_pages": 160, "output_max": 524288, "log_max": 1024, "fuel": 11_000_000, "deadline_ms": 1000,
          "max_iovecs": 16, "max_table": 10000}
_TICK_MS = 10   # the epoch ticker's period: the deadline is LIMITS["deadline_ms"] / _TICK_MS ticks

# The two profiles: every import a module may declare, with its exact signature (= host_core.mjs PROFILES)
PROFILES = {
    "pp": {"module": "pp", "entry": ("run", "->i32"),
           "imports": {"read_input": "i32,i32->i32", "write_output": "i32,i32->", "log": "i32,i32->"}},
    "javy": {"module": "wasi_snapshot_preview1", "entry": ("_start", "->"),
             "imports": {"fd_read": "i32,i32,i32,i32->i32", "fd_write": "i32,i32,i32,i32->i32", "proc_exit": "i32->",
                         "environ_get": "i32,i32->i32", "environ_sizes_get": "i32,i32->i32",
                         "clock_time_get": "i32,i64,i32->i32", "fd_close": "i32->i32",
                         "fd_fdstat_get": "i32,i32->i32", "fd_seek": "i32,i64,i32,i32->i32"}},
}
FORBIDDEN_AT_CALL = {"clock_time_get", "fd_close", "fd_fdstat_get", "fd_seek"}
_VALTYPES = {0x7F: "i32", 0x7E: "i64", 0x7D: "f32", 0x7C: "f64", 0x7B: "v128", 0x70: "funcref", 0x6F: "externref"}

# wasmtime's trap codes, named as host_core.mjs `trapName` names the browser's
_TRAP_NAMES = {
    wasmtime.TrapCode.STACK_OVERFLOW: "stack_overflow",
    wasmtime.TrapCode.MEMORY_OUT_OF_BOUNDS: "memory_out_of_bounds",
    wasmtime.TrapCode.UNREACHABLE: "unreachable",
    wasmtime.TrapCode.OUT_OF_FUEL: "out_of_fuel",
    wasmtime.TrapCode.INTERRUPT: "timeout",          # the epoch deadline: the browser's Worker timeout, same name
    wasmtime.TrapCode.INTEGER_DIVISION_BY_ZERO: "integer_division_by_zero",
    wasmtime.TrapCode.INTEGER_OVERFLOW: "integer_overflow",
    wasmtime.TrapCode.BAD_CONVERSION_TO_INTEGER: "bad_conversion_to_integer",
}


class Refused(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class _HostTrap(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class _Exit(Exception):
    def __init__(self, code: int):
        super().__init__(f"exit {code}")
        self.code = code


_ENGINE = None


def engine() -> wasmtime.Engine:
    """ONE engine per process, fuel on, with a WALL-CLOCK deadline beside it: fuel does not price work done inside our
    host functions (measured: wasmtime 49's fuel DOES price a bulk memory fill's length), so a daemon ticker advances
    the engine's epoch every 10 ms and each call traps `timeout` after LIMITS["deadline_ms"] — the browser's Worker
    timeout, the same value."""
    global _ENGINE
    if _ENGINE is None:
        config = wasmtime.Config()
        config.consume_fuel = True
        config.epoch_interruption = True
        eng = wasmtime.Engine(config)

        def tick():
            while True:
                time.sleep(_TICK_MS / 1000)
                eng.increment_epoch()
        threading.Thread(target=tick, name="pp_wasm-epoch", daemon=True).start()
        _ENGINE = eng
    return _ENGINE


class Loaded:
    def __init__(self, module: wasmtime.Module, profile: str, engine_: wasmtime.Engine, metered: bool):
        self.module, self.profile, self.engine, self.metered = module, profile, engine_, metered


def shape(b: bytes) -> dict:
    """THE SHAPE — read from the module's bytes by the same steps, in the same order, as host_core.mjs `shape`, so both
    hosts refuse the same modules with the same reason."""
    pos = [0]

    def fail(reason):
        raise Refused(reason)

    def u8():
        if pos[0] >= len(b):
            fail("invalid_module truncated")
        pos[0] += 1
        return b[pos[0] - 1]

    def leb():
        r = sh = 0
        while True:
            x = u8()
            r += (x & 0x7F) << sh
            sh += 7
            if not x & 0x80:
                return r

    def name():
        n = leb()
        s = bytes(b[pos[0]: pos[0] + n]).decode("utf-8", "replace")
        pos[0] += n
        return s

    def valtype():
        return _VALTYPES.get(u8()) or fail("unsupported_type")

    def limits():
        f = u8()
        lo = leb()
        return {"flags": f, "min": lo, "max": leb() if f & 1 else None}

    if len(b) < 8 or b[:5] != b"\0asm\x01":
        fail("invalid_module header")
    pos[0] = 8
    m = {"types": [], "imports": [], "funcs": [], "tables": [], "memories": [], "exports": [], "start": False}
    while pos[0] < len(b):
        sid = u8()
        size = leb()
        end = pos[0] + size
        if sid == 1:
            for _ in range(leb()):
                if u8() != 0x60:
                    fail("unsupported_type")
                params = [valtype() for _ in range(leb())]
                results = [valtype() for _ in range(leb())]
                m["types"].append(",".join(params) + "->" + ",".join(results))
        elif sid == 2:
            for _ in range(leb()):
                imp = {"module": name(), "name": name(), "kind": u8()}
                if imp["kind"] == 0:
                    imp["type"] = leb()
                elif imp["kind"] == 1:
                    u8()
                    limits()
                elif imp["kind"] == 2:
                    limits()
                elif imp["kind"] == 3:
                    valtype()
                    u8()
                else:
                    fail(f"undeclared_import {imp['module']}.{imp['name']}")
                m["imports"].append(imp)
        elif sid == 3:
            m["funcs"] = [leb() for _ in range(leb())]
        elif sid == 4:
            for _ in range(leb()):
                ref = u8()
                m["tables"].append({"ref": ref, **limits()})
        elif sid == 5:
            m["memories"] = [limits() for _ in range(leb())]
        elif sid == 7:
            for _ in range(leb()):
                m["exports"].append({"name": name(), "kind": u8(), "index": leb()})
        elif sid == 8:
            m["start"] = True
        elif sid not in (0, 6, 9, 10, 11, 12):
            fail(f"unsupported_section {sid}")
        pos[0] = end
    return m


def inspect(b: bytes, metered: bool = False) -> str:
    """The load-time checks (CONTRACT §5), in host_core.mjs `inspect`'s order. Returns the profile or raises Refused."""
    m = shape(b)
    imported = [x for x in m["imports"] if x["kind"] == 0]

    def func_type(i):
        return m["types"][imported[i]["type"] if i < len(imported) else m["funcs"][i - len(imported)]]

    def exp(n):
        return next((e for e in m["exports"] if e["name"] == n), None)
    profile = None
    for key, pr in PROFILES.items():
        e = exp(pr["entry"][0])
        if e and e["kind"] == 0:
            if func_type(e["index"]) != pr["entry"][1]:
                raise Refused(f"bad_signature {pr['entry'][0]}")
            profile = key
            break
    if not profile:
        raise Refused("missing_export run")
    pr = PROFILES[profile]
    seen = set()
    for imp in m["imports"]:
        ident = f"{imp['module']}.{imp['name']}"
        if imp["kind"] != 0 or imp["module"] != pr["module"] or imp["name"] not in pr["imports"]:
            raise Refused(f"undeclared_import {ident}")
        if ident in seen:
            raise Refused(f"duplicate_import {ident}")
        seen.add(ident)
        if m["types"][imp["type"]] != pr["imports"][imp["name"]]:
            raise Refused(f"bad_signature {ident}")
    if m["start"]:
        raise Refused("start_section")
    if len(m["tables"]) > 1 or any(t["ref"] != 0x70 or t["flags"] != 1 or t["max"] > LIMITS["max_table"]
                                   for t in m["tables"]):
        raise Refused("table_limit")
    mem_export = exp("memory")
    if len(m["memories"]) != 1 or m["memories"][0]["flags"] & ~1 or not mem_export or mem_export["kind"] != 2 \
            or mem_export["index"] != 0:
        raise Refused("no_memory")
    mem = m["memories"][0]
    if mem["max"] is None or mem["max"] > LIMITS["max_pages"] or mem["min"] > LIMITS["max_pages"]:
        raise Refused("no_memory_max")
    if metered:
        g = exp("pp_fuel")
        if not g or g["kind"] != 3:
            raise Refused("not_metered")
    return profile


def load(eng: wasmtime.Engine, wasm: bytes, metered: bool = False) -> Loaded:
    """The shape first (from the bytes, as the browser does), then compile. ``metered`` is the publish manifest's word
    for this module — never the module's own exports (CONTRACT §5)."""
    profile = inspect(wasm, metered)
    try:
        module = wasmtime.Module(eng, wasm)
    except wasmtime.WasmtimeError as e:
        raise Refused(f"invalid_module {str(e)[:80]}") from None
    return Loaded(module, profile, eng, metered)


class _State:
    def __init__(self, data: bytes):
        self.input, self.in_pos = data, 0
        self.out, self.out_len, self.log, self.log_len = [], 0, [], 0
        self.started = False


def _mem(caller, st: _State) -> wasmtime.Memory:
    if not st.started:
        raise _HostTrap("call_during_start")
    return caller.get("memory")


def _view(caller, st: _State, ptr: int, length: int) -> tuple[wasmtime.Memory, int, int]:
    """Bounds-checked (memory, start, stop). ⚠ wasmtime-py's Memory.read CLAMPS an out-of-range slice silently, so
    the check is ours (the browser's typed-array view throws on its own; both name it memory_out_of_bounds)."""
    m = _mem(caller, st)
    ptr, length = ptr & 0xFFFFFFFF, length & 0xFFFFFFFF
    if ptr + length > m.data_len(caller):
        raise _HostTrap("memory_out_of_bounds")
    return m, ptr, ptr + length


def _emit(caller, st: _State, which: str, m: wasmtime.Memory, a: int, b: int) -> None:
    """The answer (capped: more traps) or the log (cut). Only what is KEPT is read: reading a 10 MiB log range only to
    cut it to 1 KiB was host work no fuel pays for (review finding)."""
    if which == "out":
        if st.out_len + (b - a) > LIMITS["output_max"]:
            raise _HostTrap("output_too_large")
        st.out.append(bytes(m.read(caller, a, b)))
        st.out_len += b - a
    else:
        keep = max(0, min(b - a, LIMITS["log_max"] - st.log_len))
        if keep:
            st.log.append(bytes(m.read(caller, a, a + keep)))
            st.log_len += keep


def _u32(caller, st, ptr) -> int:
    m, a, b = _view(caller, st, ptr, 4)
    return int.from_bytes(m.read(caller, a, b), "little")


def _set_u32(caller, st, ptr, value) -> None:
    m, a, _ = _view(caller, st, ptr, 4)
    m.write(caller, (value & 0xFFFFFFFF).to_bytes(4, "little"), a)   # wraps, as the browser's setUint32 does


def _pp_funcs(st: _State) -> dict:
    def read_input(caller, ptr, length):
        m, a, b = _view(caller, st, ptr, length)
        k = min(b - a, len(st.input))
        if k:
            m.write(caller, st.input[:k], a)
        return len(st.input)

    def write_output(caller, ptr, length):
        _emit(caller, st, "out", *_view(caller, st, ptr, length))

    def log(caller, ptr, length):
        _emit(caller, st, "log", *_view(caller, st, ptr, length))

    return {"read_input": read_input, "write_output": write_output, "log": log}


def _javy_funcs(st: _State) -> dict:
    def fd_read(caller, fd, iovs, n, nread):
        if fd != 0:
            raise _HostTrap(f"forbidden_call fd_read({fd})")
        if n & 0xFFFFFFFF > LIMITS["max_iovecs"]:
            raise _HostTrap("too_many_iovecs")
        total = 0
        for i in range(n):
            m, a, b = _view(caller, st, _u32(caller, st, iovs + 8 * i), _u32(caller, st, iovs + 8 * i + 4))
            k = min(b - a, len(st.input) - st.in_pos)
            if k:
                m.write(caller, st.input[st.in_pos: st.in_pos + k], a)
            st.in_pos += k
            total += k
        _set_u32(caller, st, nread, total)
        return 0

    def fd_write(caller, fd, iovs, n, nwritten):
        if fd not in (1, 2):
            raise _HostTrap(f"forbidden_call fd_write({fd})")
        if n & 0xFFFFFFFF > LIMITS["max_iovecs"]:
            raise _HostTrap("too_many_iovecs")
        total = 0
        for i in range(n):
            m, a, b = _view(caller, st, _u32(caller, st, iovs + 8 * i), _u32(caller, st, iovs + 8 * i + 4))
            _emit(caller, st, "out" if fd == 1 else "log", m, a, b)
            total += b - a
        _set_u32(caller, st, nwritten, total)
        return 0

    def proc_exit(caller, code):
        raise _Exit(code)

    def environ_sizes_get(caller, count_ptr, size_ptr):  # an EMPTY environment, as a constant (host_core.mjs)
        _set_u32(caller, st, count_ptr, 0)
        _set_u32(caller, st, size_ptr, 0)
        return 0

    def environ_get(caller, *_):
        return 0

    funcs = {"fd_read": fd_read, "fd_write": fd_write, "proc_exit": proc_exit,
             "environ_sizes_get": environ_sizes_get, "environ_get": environ_get}
    for name in FORBIDDEN_AT_CALL:
        def forbidden(caller, *_, _n=name):
            raise _HostTrap(f"forbidden_call {_n}")
        funcs[name] = forbidden
    return funcs


def run_once(loaded: Loaded, data: bytes, fuel: int | None = None) -> dict:
    """One call: a FRESH store and instance, the input, the answer. Never raises: every end is a status + reason.

    A METERED module (``loaded.metered``, the publish manifest's word: tools/meter) carries its own counter, the
    exported i64 global ``pp_fuel``: it is the bound (set before the call, read after, a trap with it below zero is
    out_of_fuel — at the same instruction as in the browser), and wasmtime's own fuel becomes a backstop 100 x larger
    that the module's counter always beats. Beside both, the epoch deadline (``engine()``) ends a call by wall clock."""
    bound = LIMITS["fuel"] if fuel is None else fuel
    metered = loaded.metered
    st = _State(data)
    store = wasmtime.Store(loaded.engine)
    store.set_limits(memory_size=LIMITS["max_pages"] * 65536)
    store.set_fuel(bound * 100 if metered else bound)
    store.set_epoch_deadline(max(1, LIMITS["deadline_ms"] // _TICK_MS))
    status, reason, mem_bytes = "ok", None, None
    t0 = time.perf_counter()
    t1 = t0
    instance = None
    try:
        linker = wasmtime.Linker(loaded.engine)
        funcs = _pp_funcs(st) if loaded.profile == "pp" else _javy_funcs(st)
        for imp in loaded.module.imports:
            linker.define_func(imp.module, imp.name, imp.type, funcs[imp.name], access_caller=True)
        instance = linker.instantiate(store, loaded.module)
        t1 = time.perf_counter()
        st.started = True
        exports = instance.exports(store)
        if metered:
            exports["pp_fuel"].set_value(store, wasmtime.Val.i64(bound))
        if loaded.profile == "pp":
            rc = exports["run"](store)
            if rc != 0:
                status, reason = "trap", f"nonzero_exit {rc}"
        else:
            exports["_start"](store)
    except _Exit as e:
        if e.code != 0:
            status, reason = "trap", f"forbidden_call proc_exit({e.code})"
    except _HostTrap as e:
        status, reason = "trap", e.reason
    except wasmtime.Trap as e:
        status, reason = "trap", _TRAP_NAMES.get(e.trap_code, f"trap {e.message[:120]}")
    except wasmtime.WasmtimeError as e:
        status, reason = "trap", f"instantiate_failed {str(e)[:120]}"
    except Exception as e:  # noqa: BLE001 — our own code failed: named, never raised to the caller (host_core.mjs too)
        status, reason = "trap", f"host_error {type(e).__name__}"
    if t1 == t0:
        t1 = time.perf_counter()
    t2 = time.perf_counter()
    meter_used = None
    if instance is not None:
        mem = instance.exports(store).get("memory")
        mem_bytes = mem.data_len(store) if isinstance(mem, wasmtime.Memory) else None
        if metered:
            left = instance.exports(store)["pp_fuel"].value(store)
            meter_used = bound - left
            if status == "trap" and left < 0:
                reason = "out_of_fuel"
    return {
        "status": status, "reason": reason,
        "output": b"".join(st.out) if status == "ok" else None,
        "log": b"".join(st.log).decode("utf-8", "replace"),
        "fuel_used": (bound * 100 if metered else bound) - store.get_fuel(), "meter_used": meter_used,
        "instantiate_ms": (t1 - t0) * 1000, "run_ms": (t2 - t1) * 1000, "memory_bytes": mem_bytes,
    }
