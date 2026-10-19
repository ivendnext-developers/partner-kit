"""scan.py — reads every instruction of a module's code, for the kit's admission.

What the load checks (``host.py`` ``inspect``) cannot see, because they read only a module's declarations:
  * the instructions a price or decision point may not use: SIMD, atomics and floating point (P-WASM §4: none was
    exercised by the spike, and a float's result can differ by host);
  * any instruction outside the core set this host knows (exceptions, garbage collection, tail calls…).
(The stack bound is not decided here: it is the in-module counter of `stackmeter/`. A static call graph was measured
to call ordinary Rust recursive, through the indirect calls of its formatting code — so it decides nothing.)

Pure Python, no dependency. ``scan(bytes) -> dict``; raises ``ValueError`` on a malformed body.
"""

from __future__ import annotations

_FLOAT_TYPES = {0x7D, 0x7C}                     # f32, f64
_FLOAT_OPS = (set(range(0x5B, 0x67))            # f32/f64 comparisons
              | set(range(0x8B, 0xA7))          # f32/f64 arithmetic
              | {0xA8, 0xA9, 0xAA, 0xAB, 0xAE, 0xAF, 0xB0, 0xB1}   # trunc float → int
              | set(range(0xB2, 0xC0))          # convert / demote / promote / reinterpret
              | {0x2A, 0x2B, 0x38, 0x39, 0x43, 0x44})              # float loads, stores, constants
_NO_IMM = ({0x00, 0x01, 0x05, 0x0B, 0x0F, 0x1A, 0x1B, 0xD1} | set(range(0x45, 0xC5)))
_MEMARG = set(range(0x28, 0x3F))


class _R:
    def __init__(self, b, pos=0, end=None):
        self.b, self.pos, self.end = b, pos, len(b) if end is None else end

    def u8(self):
        if self.pos >= self.end:
            raise ValueError("truncated")
        self.pos += 1
        return self.b[self.pos - 1]

    def leb(self):
        r = sh = 0
        while True:
            x = self.u8()
            r |= (x & 0x7F) << sh
            sh += 7
            if not x & 0x80:
                return r

    def skip(self, n):
        self.pos += n


def _sections(b: bytes):
    r = _R(b, 8)
    while r.pos < len(b):
        sid, size = r.u8(), r.leb()
        yield sid, r.pos, r.pos + size
        r.pos += size


def scan(b: bytes) -> dict:
    n_imported_funcs, bodies = 0, []
    for sid, start, end in _sections(b):
        r = _R(b, start, end)
        if sid == 2:                                            # imports: count the imported functions
            for _ in range(r.leb()):
                for _ in range(2):
                    r.skip(r.leb())
                kind = r.u8()
                if kind == 0:
                    n_imported_funcs += 1
                    r.leb()
                elif kind == 1:
                    r.u8()
                    f = r.u8(); r.leb(); f & 1 and r.leb()
                elif kind == 2:
                    f = r.u8(); r.leb(); f & 1 and r.leb()
                else:
                    r.u8(); r.u8()
        elif sid == 10:
            for _ in range(r.leb()):
                size = r.leb()
                bodies.append((r.pos, r.pos + size))
                r.pos += size
    found = {"float": [], "simd": 0, "atomics": 0, "unsupported": set()}
    for i, (s, e) in enumerate(bodies):
        fidx = n_imported_funcs + i
        r = _R(b, s, e)
        for _ in range(r.leb()):                                # locals
            r.leb()
            if r.u8() in _FLOAT_TYPES:
                found["float"].append(f"func {fidx}: a float local")
        while r.pos < e:
            op = r.u8()
            if op in _FLOAT_OPS:
                found["float"].append(f"func {fidx}: opcode 0x{op:02x}")
            if op in _NO_IMM:
                continue
            if op in (0x02, 0x03, 0x04):                        # block type
                bt = r.u8()
                if bt not in (0x40, 0x7F, 0x7E, 0x7D, 0x7C, 0x7B, 0x70, 0x6F):
                    r.pos -= 1; r.leb()
            elif op in (0x0C, 0x0D, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0xD2):
                r.leb()
            elif op == 0x0E:
                for _ in range(r.leb() + 1):
                    r.leb()
            elif op == 0x10:
                r.leb()
            elif op == 0x11:
                r.leb(); r.leb()
            elif op == 0x1C:
                for _ in range(r.leb()):
                    r.u8()
            elif op in _MEMARG:
                r.leb(); r.leb()
            elif op in (0x3F, 0x40):
                r.u8()
            elif op == 0x41 or op == 0x42:
                r.leb()
            elif op == 0x43:
                r.skip(4)
            elif op == 0x44:
                r.skip(8)
            elif op == 0xD0:
                r.u8()
            elif op == 0xFC:
                sub = r.leb()
                if sub <= 7:
                    found["float"].append(f"func {fidx}: saturating float truncation")
                elif sub == 8:
                    r.leb(); r.u8()
                elif sub in (9, 13, 15, 16, 17):
                    r.leb()
                elif sub in (10,):
                    r.u8(); r.u8()
                elif sub == 11:
                    r.u8()
                elif sub in (12, 14):
                    r.leb(); r.leb()
                else:
                    found["unsupported"].add(f"0xfc {sub}")
            elif op == 0xFD:                                    # read to the end: a server-only point may use SIMD
                found["simd"] += 1
                sub = r.leb()
                if sub <= 11 or sub in (92, 93):
                    r.leb(); r.leb()                            # memarg
                elif sub in (12, 13):
                    r.skip(16)                                  # v128.const · i8x16.shuffle
                elif 21 <= sub <= 34:
                    r.u8()                                      # lane index
                elif 84 <= sub <= 91:
                    r.leb(); r.leb(); r.u8()                    # memarg + lane
            elif op == 0xFE:
                found["atomics"] += 1                           # refused whatever follows: stop reading this body
                break
            else:
                found["unsupported"].add(f"0x{op:02x}")
                break
    found["unsupported"] = sorted(found["unsupported"])
    found["functions"] = len(bodies)
    return found


if __name__ == "__main__":
    import json
    import sys
    for p in sys.argv[1:]:
        print(p, json.dumps(scan(open(p, "rb").read())))
