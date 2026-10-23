"""The Wasm scan: each instruction a price or decision point may not use is found, and nothing else is.

    python3 -m unittest discover -s tools/wasm_kit/tests

``scan.py`` is what ``tools/check/check.py`` and ``kit.py publish`` read a module with. Each module here is built byte by
byte (no Rust, no assembler), so every case runs on a laptop with Python alone. The immediates are chosen to hold bytes
that are themselves opcodes (0x92 is f32.add, 0xFE the atomics prefix): a scan that loses its place reads them as
instructions, and a test goes red.
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from scan import scan  # noqa: E402

HEADER = b"\x00asm\x01\x00\x00\x00"
END, DROP, NOP = 0x0B, 0x1A, 0x01
F32, F64, I32 = 0x7D, 0x7C, 0x7F


def leb(n: int) -> bytes:
    out = bytearray()
    while True:
        b, n = n & 0x7F, n >> 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def section(sid: int, payload: bytes) -> bytes:
    return bytes([sid]) + leb(len(payload)) + payload


def vec(items) -> bytes:
    items = list(items)
    return leb(len(items)) + b"".join(items)


def name(s: str) -> bytes:
    return leb(len(s)) + s.encode()


def body(code: bytes, locals_: tuple = ()) -> bytes:
    """One function body: its local declarations (count, type), its code and the closing ``end``."""
    inner = vec(leb(n) + bytes([t]) for n, t in locals_) + code + bytes([END])
    return leb(len(inner)) + inner


def module(*bodies: bytes, imports: tuple = ()) -> bytes:
    """One type ``() -> ()``; every function, imported or not, has it."""
    out = HEADER + section(1, vec([b"\x60\x00\x00"]))
    if imports:
        out += section(2, vec(imports))
    out += section(3, vec(b"\x00" for _ in bodies))
    return out + section(10, vec(bodies))


IMPORT_FUNC = name("env") + name("f") + b"\x00" + leb(0)
IMPORT_TABLE = name("env") + name("t") + b"\x01\x70\x01" + leb(1) + leb(8)   # funcref, min 1, max 8
IMPORT_MEMORY = name("env") + name("m") + b"\x02\x01" + leb(1) + leb(2)       # min 1, max 2
IMPORT_GLOBAL = name("env") + name("g") + b"\x03" + bytes([I32, 0])           # i32, immutable

CLEAN = {"float": [], "simd": 0, "atomics": 0, "unsupported": []}


def found(*bodies, imports=()):
    r = scan(module(*bodies, imports=imports))
    return {k: r[k] for k in CLEAN}, r["functions"]


class Clean(unittest.TestCase):
    def test_an_empty_function_is_clean(self):
        self.assertEqual(found(body(b"")), (CLEAN, 1))

    def test_integer_code_is_clean(self):
        code = (b"\x41" + leb(7) + b"\x41" + leb(5) + b"\x6a" + bytes([DROP])        # i32.const 7, i32.const 5, i32.add
                + b"\x42" + leb(1) + b"\x42" + leb(2) + b"\x7c" + bytes([DROP]))     # the same on i64
        self.assertEqual(found(body(code)), (CLEAN, 1))

    def test_immediates_that_look_like_opcodes_are_not_read_as_instructions(self):
        cases = {
            "i32.const 0x92 (f32.add)": b"\x41\x92\x01" + bytes([DROP]),
            "i32.const 0xFE (atomics)": b"\x41\xfe\x01" + bytes([DROP]),
            "i64.const 0xFD (SIMD)": b"\x42\xfd\x01" + bytes([DROP]),
            "local.get 0x92": b"\x20\x92\x01" + bytes([DROP]),
            "a memarg of 0x92": b"\x41\x00\x28\x02\x92\x01" + bytes([DROP]),     # i32.load align 2, offset 146
            "call 0xFE": b"\x10\xfe\x01",
            # seven blocks deep, so a br_table's default label may be 6, the byte of try (exceptions)
            "a br_table default of 6 (try)": b"\x02\x40" * 7 + b"\x41\x00\x0e\x00\x06" + bytes([END]) * 7,
        }
        for what, code in cases.items():
            with self.subTest(what):
                locals_ = ((147, I32),) if "local" in what else ()
                self.assertEqual(found(body(code, locals_))[0], CLEAN)

    def test_blocks_branches_and_bulk_memory_are_clean(self):
        code = (b"\x02\x40"                                    # block (no result)
                + b"\x03\x7f" + b"\x41\x01" + bytes([END])     # loop (result i32) … end
                + bytes([DROP])
                + b"\x41\x00\x0e\x02\x00\x00\x00"              # br_table, two targets and a default
                + bytes([END])
                + b"\x41\x00\x41\x00\x41\x00\xfc\x0a\x00\x00"  # memory.copy
                + b"\x41\x00\x41\x00\x41\x00\xfc\x0b\x00")     # memory.fill
        self.assertEqual(found(body(code))[0], CLEAN)


class Refused(unittest.TestCase):
    def test_a_float_instruction_is_found_with_its_function_and_opcode(self):
        code = b"\x43" + b"\x00\x00\x80\x3f" + b"\x43" + b"\x00\x00\x00\x40" + b"\x92" + bytes([DROP])
        f = found(body(code))[0]["float"]
        self.assertIn("func 0: opcode 0x43", f)
        self.assertIn("func 0: opcode 0x92", f)

    def test_an_f64_constant_is_skipped_whole(self):
        code = b"\x44" + b"\xfe" * 8 + bytes([DROP])           # eight bytes of 0xFE: not eight atomics
        f = found(body(code))[0]
        self.assertEqual((f["atomics"], f["unsupported"]), (0, []))
        self.assertEqual(f["float"], ["func 0: opcode 0x44"])

    def test_a_float_local_is_found_though_no_instruction_uses_it(self):
        for t in (F32, F64):
            with self.subTest(hex(t)):
                self.assertEqual(found(body(b"", ((1, t),)))[0]["float"], ["func 0: a float local"])

    def test_each_saturating_truncation_is_a_float(self):
        for sub in range(8):                                   # 0xFC 0 to 7: f32 and f64 to i32 and i64, signed and not
            with self.subTest(sub):
                f = found(body(b"\x44" + b"\x00" * 8 + b"\xfc" + leb(sub) + bytes([DROP])))[0]["float"]
                self.assertIn("func 0: saturating float truncation", f)

    def test_simd_is_counted_and_the_scan_reads_on(self):
        code = (b"\xfd\x0c" + b"\xfe" * 16 + bytes([DROP])   # v128.const: sixteen bytes that are not atomics
                + b"\x43\x00\x00\x00\x00" + bytes([DROP]))   # and a float after it, still found
        f = found(body(code))[0]
        self.assertEqual((f["simd"], f["atomics"], f["unsupported"]), (1, 0, []))
        self.assertEqual(f["float"], ["func 0: opcode 0x43"])

    def test_atomics_are_counted_and_the_next_function_is_still_read(self):
        f = found(body(b"\x41\x00\xfe\x10\x02\x00" + bytes([DROP])),   # i32.atomic.load
                  body(b"\x43\x00\x00\x00\x00" + bytes([DROP])))[0]
        self.assertEqual(f["atomics"], 1)
        self.assertEqual(f["float"], ["func 1: opcode 0x43"])

    def test_an_instruction_outside_the_core_set_is_named(self):
        cases = {
            "try (exceptions)": (b"\x06\x40" + bytes([END]), ["0x06"]),
            "return_call (tail calls)": (b"\x12\x00", ["0x12"]),
            "an unknown 0xFC instruction": (b"\xfc\x14", ["0xfc 20"]),
        }
        for what, (code, want) in cases.items():
            with self.subTest(what):
                self.assertEqual(found(body(code))[0]["unsupported"], want)


class Imports(unittest.TestCase):
    def test_imported_functions_come_first_in_the_numbering(self):
        f = found(body(b""), body(b"\x43\x00\x00\x00\x00" + bytes([DROP])), imports=(IMPORT_FUNC, IMPORT_FUNC))
        self.assertEqual(f, ({**CLEAN, "float": ["func 3: opcode 0x43"]}, 2))

    def test_a_table_a_memory_and_a_global_are_not_counted_as_functions(self):
        imports = (IMPORT_TABLE, IMPORT_MEMORY, IMPORT_GLOBAL, IMPORT_FUNC)
        f = found(body(b"\x43\x00\x00\x00\x00" + bytes([DROP])), imports=imports)
        self.assertEqual(f, ({**CLEAN, "float": ["func 1: opcode 0x43"]}, 1))


class Malformed(unittest.TestCase):
    def test_a_body_cut_short_raises(self):
        inner = b"\x00" + b"\x41\x80"                          # no locals; an i32.const whose value says "more follows"
        cut = HEADER + section(1, vec([b"\x60\x00\x00"])) + section(3, vec([b"\x00"])) \
            + section(10, vec([leb(len(inner)) + inner]))
        with self.assertRaises(ValueError):
            scan(cut)

    def test_a_section_longer_than_the_file_never_scans_clean(self):
        # check.py refuses whatever the scanner raises here; what matters is that it never returns a clean result
        with self.assertRaises((ValueError, IndexError)):
            scan(HEADER + bytes([10, 5, 1]))


if __name__ == "__main__":
    unittest.main()
