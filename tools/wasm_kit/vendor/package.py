# Source: ivendnext/partner-programme spikes/wasm/tools/package.py @ 2799842dca46, vendored: its one home is there. A defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository).
"""package.py — the publish step for a partner adjuster module (from the WebAssembly spike). Python standard library only.

It does one thing to the module: it WRITES THE MEMORY MAXIMUM. A browser cannot cap a module's memory any other way,
so the cap must be inside the module, where both hosts read the same number (CONTRACT §5, `no_memory_max`).
A module that already declares a smaller maximum keeps it; one whose initial memory is above the cap is refused.
It then records the module's size, sha256 and whether it carries the fuel counter (`--metered`, given by the build
after tools/meter ran) in `modules/MANIFEST.json`. The hosts take "metered" from this record, never from the module's
own exports: a module could export a global of that name to claim a 100x larger server bound (review finding 5).

    python3 tools/package.py <in.wasm> <out.wasm> [--max-pages 160] [--metered]
"""
import hashlib
import json
import os
import sys

MAX_PAGES = 160  # 10 MiB, CONTRACT §5


def leb_read(b: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = b[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return result, pos


def leb_write(n: int) -> bytes:
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def set_memory_max(wasm: bytes, max_pages: int) -> tuple[bytes, dict]:
    if wasm[:4] != b"\0asm":
        raise SystemExit("REFUSED: not a WebAssembly module")
    pos, out = 8, bytearray(wasm[:8])
    found = None
    while pos < len(wasm):
        sid = wasm[pos]
        size, body = leb_read(wasm, pos + 1)
        end = body + size
        section = wasm[body:end]
        if sid == 5:
            count, p = leb_read(section, 0)
            flags = section[p]
            if count != 1 or flags & ~1:
                raise SystemExit("REFUSED: one plain 32-bit memory is required")
            initial, p = leb_read(section, p + 1)
            declared = leb_read(section, p)[0] if flags & 1 else None
            if initial > max_pages:
                raise SystemExit(f"REFUSED: initial memory {initial} pages is above the cap {max_pages}")
            new_max = max_pages if declared is None else min(declared, max_pages)
            section = leb_write(1) + b"\x01" + leb_write(initial) + leb_write(new_max)
            found = {"initial_pages": initial, "declared_max_pages": declared, "max_pages": new_max}
        out += bytes([sid]) + leb_write(len(section)) + section
        pos = end
    if found is None:
        raise SystemExit("REFUSED: the module defines no memory of its own")
    return bytes(out), found


def main(argv: list[str]) -> None:
    src, dst = argv[1], argv[2]
    cap = int(argv[argv.index("--max-pages") + 1]) if "--max-pages" in argv else MAX_PAGES
    raw = open(src, "rb").read()
    packed, memory = set_memory_max(raw, cap)
    open(dst, "wb").write(packed)
    manifest_path = os.path.join(os.path.dirname(dst), "MANIFEST.json")
    manifest = json.load(open(manifest_path)) if os.path.exists(manifest_path) else {}
    manifest[os.path.basename(dst)] = {
        "bytes": len(packed), "sha256": hashlib.sha256(packed).hexdigest(),
        "source_bytes": len(raw), "source_sha256": hashlib.sha256(raw).hexdigest(), "memory": memory,
        "metered": "--metered" in argv,
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")
    print(f"packaged {os.path.basename(dst)}: {len(packed)} bytes, memory {memory}")


if __name__ == "__main__":
    main(sys.argv)
