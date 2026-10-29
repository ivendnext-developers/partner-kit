"""A QR code for a table's link, as a picture the retailer prints (standard library only).

The retailer's iVendNext has no QR maker a print format may call, and a print format may load nothing from outside the
shop, so the service draws each table's code itself and writes it on the code's record as a ``data:`` picture (an SVG),
which the record's form shows and its print format prints.

Byte mode, error correction level M (about 15% of the code may be damaged and it still reads), versions 1 to 10 (up to
213 bytes; a table's link is about 110). The steps and the tables are the standard's (ISO/IEC 18004), in the order a
reader of the standard expects them; the mask is chosen by three of the standard's four penalty rules (runs, blocks,
balance), which every phone camera reads. ``matrix(text)`` is the grid (True = dark); ``svg_data_uri(text)`` the picture.
"""

from __future__ import annotations

import base64

# per version 1..10 at level M: error correction codewords per block, and the number of blocks
_ECC_PER_BLOCK = (None, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26)
_BLOCKS = (None, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5)
_FORMAT_M = 0                      # level M's two format bits
MOST_VERSION = 10


def _raw_modules(ver: int) -> int:
    n = (16 * ver + 128) * ver + 64
    if ver >= 2:
        align = ver // 7 + 2
        n -= (25 * align - 10) * align - 55
        if ver >= 7:
            n -= 36
    return n


def _data_codewords(ver: int) -> int:
    return _raw_modules(ver) // 8 - _ECC_PER_BLOCK[ver] * _BLOCKS[ver]


def _alignment(ver: int) -> list[int]:
    if ver == 1:
        return []
    align = ver // 7 + 2
    step = (ver * 8 + align * 3 + 5) // (align * 4 - 4) * 2
    return [6] + sorted(ver * 4 + 10 - i * step for i in range(align - 1))


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> list[int]:
    out = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            out[j] = _gf_mul(out[j], root)
            if j + 1 < degree:
                out[j] ^= out[j + 1]
        root = _gf_mul(root, 0x02)
    return out


def _rs_remainder(data: list[int], divisor: list[int]) -> list[int]:
    out = [0] * len(divisor)
    for b in data:
        factor = b ^ out.pop(0)
        out.append(0)
        for i, coef in enumerate(divisor):
            out[i] ^= _gf_mul(coef, factor)
    return out


def _codewords(text: bytes) -> tuple[int, list[int]]:
    """(the smallest version that holds the text, its data and error correction codewords, interleaved)."""
    for ver in range(1, MOST_VERSION + 1):
        count_bits = 8 if ver <= 9 else 16
        if 4 + count_bits + 8 * len(text) <= _data_codewords(ver) * 8:
            break
    else:
        raise ValueError(f"too long for a table's code: {len(text)} bytes (at most 213)")
    bits = [0, 1, 0, 0] + [(len(text) >> i) & 1 for i in reversed(range(count_bits))]
    for b in text:
        bits += [(b >> i) & 1 for i in reversed(range(8))]
    room = _data_codewords(ver) * 8
    bits += [0] * min(4, room - len(bits))
    bits += [0] * (-len(bits) % 8)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(data) < _data_codewords(ver):
        data.append(pad)
        pad ^= 0xEC ^ 0x11
    blocks, ecc_len = _BLOCKS[ver], _ECC_PER_BLOCK[ver]
    raw = _raw_modules(ver) // 8
    short = blocks - raw % blocks
    short_len = raw // blocks
    divisor = _rs_divisor(ecc_len)
    out, k = [], 0
    for i in range(blocks):
        dat = data[k:k + short_len - ecc_len + (0 if i < short else 1)]
        k += len(dat)
        ecc = _rs_remainder(dat, divisor)
        if i < short:
            dat = dat + [0]
        out.append(dat + ecc)
    woven = []
    for i in range(len(out[0])):
        for j, blk in enumerate(out):
            if i != short_len - ecc_len or j >= short:
                woven.append(blk[i])
    return ver, woven


class _Grid:
    def __init__(self, ver: int):
        self.size = ver * 4 + 17
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.fixed = [[False] * self.size for _ in range(self.size)]

    def put(self, x: int, y: int, dark: bool):
        self.dark[y][x], self.fixed[y][x] = dark, True


def _function_patterns(g: _Grid, ver: int):
    n = g.size
    for i in range(n):
        g.put(6, i, i % 2 == 0)
        g.put(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < n and 0 <= y < n:
                    g.put(x, y, max(abs(dx), abs(dy)) not in (2, 4))
    pos = _alignment(ver)
    last = len(pos) - 1
    for i, ax in enumerate(pos):
        for j, ay in enumerate(pos):
            if (i, j) in ((0, 0), (0, last), (last, 0)):
                continue                # a finder sits there
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    g.put(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
    _format_bits(g, 0)
    if ver >= 7:
        rem = ver
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = ver << 12 | rem
        for i in range(18):
            bit = (bits >> i) & 1 == 1
            a, b = n - 11 + i % 3, i // 3
            g.put(a, b, bit)
            g.put(b, a, bit)


def _format_bits(g: _Grid, mask: int):
    data = _FORMAT_M << 3 | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    bits = (data << 10 | rem) ^ 0x5412
    bit = [(bits >> i) & 1 == 1 for i in range(15)]
    n = g.size
    for i in range(6):
        g.put(8, i, bit[i])
    g.put(8, 7, bit[6])
    g.put(8, 8, bit[7])
    g.put(7, 8, bit[8])
    for i in range(9, 15):
        g.put(14 - i, 8, bit[i])
    for i in range(8):
        g.put(n - 1 - i, 8, bit[i])
    for i in range(8, 15):
        g.put(8, n - 15 + i, bit[i])
    g.put(8, n - 8, True)


def _place(g: _Grid, words: list[int]):
    n, i, total = g.size, 0, len(words) * 8
    right = n - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(n):
            for j in range(2):
                x = right - j
                y = n - 1 - vert if (right + 1) & 2 == 0 else vert
                if not g.fixed[y][x] and i < total:
                    g.dark[y][x] = (words[i >> 3] >> (7 - (i & 7))) & 1 == 1
                    i += 1
        right -= 2


_MASKS = (
    lambda x, y: (x + y) % 2 == 0,
    lambda x, y: y % 2 == 0,
    lambda x, y: x % 3 == 0,
    lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0,
    lambda x, y: x * y % 2 + x * y % 3 == 0,
    lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
)


def _masked(g: _Grid, mask: int) -> list[list[bool]]:
    f = _MASKS[mask]
    return [[g.dark[y][x] ^ (not g.fixed[y][x] and f(x, y)) for x in range(g.size)] for y in range(g.size)]


def _penalty(m: list[list[bool]]) -> int:
    n, score = len(m), 0
    for line in m + [list(col) for col in zip(*m)]:     # runs of five or more alike, across and down
        run = 1
        for a, b in zip(line, line[1:]):
            if a == b:
                run += 1
            else:
                score += run - 2 if run >= 5 else 0
                run = 1
        score += run - 2 if run >= 5 else 0
    for y in range(n - 1):                               # each 2 x 2 block of one colour
        for x in range(n - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                score += 3
    dark = sum(map(sum, m))                              # the balance: 10 for each 5% away from half dark
    score += abs(dark * 20 - n * n * 10) // (n * n) * 10
    return score


def matrix(text: str, mask: int | None = None) -> list[list[bool]]:
    """The code's grid for ``text`` (True = dark), with the mask given or the one the penalty rules choose."""
    ver, words = _codewords(text.encode("utf-8"))
    g = _Grid(ver)
    _function_patterns(g, ver)
    _place(g, words)
    best = None
    for k in ([mask] if mask is not None else range(8)):
        _format_bits(g, k)
        m = _masked(g, k)
        p = _penalty(m)
        if best is None or p < best[0]:
            best = (p, k, m)
    _format_bits(g, best[1])
    return _masked(g, best[1])


def svg(text: str, module: int = 8, quiet: int = 4) -> str:
    m = matrix(text)
    side = (len(m) + 2 * quiet) * module
    rects = "".join(f"M{(x + quiet) * module} {(y + quiet) * module}h{module}v{module}h-{module}z"
                    for y, row in enumerate(m) for x, dark in enumerate(row) if dark)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {side} {side}" width="{side}" height="{side}" '
            f'shape-rendering="crispEdges"><rect width="{side}" height="{side}" fill="#fff"/>'
            f'<path fill="#000" d="{rects}"/></svg>')


def svg_data_uri(text: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg(text).encode()).decode()
