#!/usr/bin/env python3
"""ivn-kit 0.1.0 · the three page checks that sit next to the "tokens only" check (check_kit.sh runs them on every
page you give it; the default is the kit's three templates). Run on one page: tools/check_page.py <check> page.html ...

  version    the kit the page loads: its stylesheet (and script, if it loads one) must be a file next to the page, not a
             remote address, and carry the same kit version as the kit being checked
  contrast   the page's own colour pairs (a text colour and a background set in the page's <style> or style="" by
             --ivn-* tokens) read against the kit's tokens, light and dark, at the kit's 4.5:1 text floor
  rtl        the page rendered left-to-right and right-to-left in headless Chrome: every block box must land where a mirror
             image puts it, every element's margins and paddings must swap sides, the page must not scroll sideways or run past
             the window's edge, and no text may be pinned to the left or right (a part kept left-to-right on purpose with
             dir="ltr" is skipped; so are the insides of an icon)

Exit 0 = pass, 1 = fail (the output names the page, the line or box and the reason), 3 = skipped (rtl: no Chrome)."""
import html
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def show(path):
    rel = os.path.relpath(path)
    return rel if len(rel) < len(path) else path


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def markup(path):
    """The page with its HTML comments taken out: a commented-out link or style is not on the page."""
    return re.sub(r"<!--.*?-->", "", read(path), flags=re.S)


def kit_version():
    m = re.search(r"ivn-kit (\d+\.\d+\.\d+)", read(os.path.join(KIT, "ivn-kit.css"))[:400])
    return m.group(1) if m else None


# ── version ──────────────────────────────────────────────────────────────────────────────────────────────────
def asset_version(path):
    text = read(path)
    if path.endswith(".css"):
        m = re.search(r"ivn-kit (\d+\.\d+\.\d+)", text[:400])
    else:
        m = re.search(r'VERSION\s*=\s*"(\d+\.\d+\.\d+)"', text)
    return m.group(1) if m else None


def check_version(pages):
    want, bad = kit_version(), 0
    for page in pages:
        text = markup(page)
        refs = [(m.group(1), "css") for m in re.finditer(r"<link\b[^>]*\bhref\s*=\s*[\"']([^\"']*ivn-kit[^\"']*)[\"']", text, re.I)]
        refs += [(m.group(1), "js") for m in re.finditer(r"<script\b[^>]*\bsrc\s*=\s*[\"']([^\"']*ivn-kit[^\"']*)[\"']", text, re.I)]
        if not any(kind == "css" for _, kind in refs):
            bad += 1
            print("FAIL %s: the page loads no ivn-kit stylesheet, so its look is not the kit's" % show(page))
        seen = {}
        for ref, kind in refs:
            if re.match(r"^(?:[a-z][a-z0-9+.-]*:)?//", ref, re.I):
                bad += 1
                print("FAIL %s: loads the kit from a remote address (%s); the kit is a file you ship with the page" % (show(page), ref))
                continue
            path = os.path.normpath(os.path.join(os.path.dirname(page), ref.split("?")[0].split("#")[0]))
            if not os.path.isfile(path):
                bad += 1
                print("FAIL %s: %s is not a file (the page's own copy of the kit is missing)" % (show(page), ref))
                continue
            have = asset_version(path)
            seen[kind] = have
            if have != want:
                bad += 1
                print("FAIL %s: loads %s at kit version %s; this kit is %s" % (show(page), ref, have or "(no version found)", want))
        if len(set(seen.values())) > 1:
            bad += 1
            print("FAIL %s: the stylesheet and the script it loads are different kit versions (%s)" % (show(page), seen))
    print(("PASS" if not bad else "FAIL") + " kit version %s — %d page(s): %s" % (kit_version(), len(pages), ", ".join(map(show, pages))))
    return 1 if bad else 0


# ── contrast ─────────────────────────────────────────────────────────────────────────────────────────────────
TOKEN = re.compile(r"^var\(\s*(--ivn-[a-z0-9-]+)\s*\)$", re.I)


def kv(body):
    for part in body.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            yield k.strip().lower(), v.strip()


def declarations(text):
    """Yield (where, {property: value}) for every <style> rule and style="" attribute of the page."""
    for block in re.findall(r"<style\b[^>]*>(.*?)</style>", text, re.S | re.I):
        block = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", block):
            yield sel.strip()[:60], dict(kv(body))
    for m in re.finditer(r"<([a-z0-9-]+)\b[^>]*?\bstyle\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", text, re.I):
        yield "<%s style>" % m.group(1), dict(kv(m.group(2) if m.group(2) is not None else m.group(3)))


def token_of(value):
    """The --ivn-* token a colour value is, or None; a background shorthand may carry other words."""
    for word in re.findall(r"var\([^)]*\)|\S+", value):
        m = TOKEN.match(word)
        if m:
            return m.group(1)
    return None


def check_contrast(pages):
    import contrast as C
    themes = (("light", C.light), ("dark", dict(C.light, **C.dark)))
    bad, readings = 0, 0
    for page in pages:
        for where, d in declarations(markup(page)):
            fg = token_of(d["color"]) if "color" in d else None
            bg = token_of(d.get("background-color") or d.get("background") or "")
            unknown = [t for t in (fg, bg) if t is not None and t not in C.light]
            for t in unknown:
                bad += 1
                print("FAIL %s %s: %s is not a kit token" % (show(page), where, t))
            # only a text colour and a background set TOGETHER are read: one set alone has no known partner (a white label
            # on a dark button is right), so it is not judged
            if unknown or fg is None or bg is None:
                continue
            for label, tokens in themes:
                a, b = C.resolve(tokens, fg), C.resolve(tokens, bg)
                if a is None or b is None:        # "transparent": nothing to read
                    continue
                r = C.ratio(a, b)
                readings += 1
                if r < 4.5:
                    bad += 1
                    print("FAIL %s %s (%s): %s on %s = %.2f:1, under the 4.5:1 text floor" % (show(page), where, label, fg, bg, r))
    print(("PASS" if not bad else "FAIL") + " contrast on the page's own colour pairs — %d reading(s), light and dark, %d page(s)" % (readings, len(pages)))
    return 1 if bad else 0


# ── right-to-left ────────────────────────────────────────────────────────────────────────────────────────────
PROBE = """<script>(function () {
  function run() {
    var rtl = %s, root = document.documentElement;
    if (rtl) root.setAttribute("dir", "rtl");
    var rows = [], els = document.body.querySelectorAll("*");
    for (var i = 0; i < els.length; i++) {
      var e = els[i], t = e.tagName;
      if (t === "SCRIPT" || t === "STYLE" || t === "LINK" || t === "META") continue;
      var r = e.getBoundingClientRect(), cs = getComputedStyle(e);
      // boxes only: text running inline and the inside of an icon follow the text's own bidi order, not a mirror
      if (e instanceof SVGElement || e.closest('[dir="ltr"]')) continue;     // an island kept left-to-right on purpose
      var inline = cs.display === "inline";
      if (r.width < 1 && !inline || r.height < 1 && !inline || cs.visibility === "hidden") continue;
      var name = t.toLowerCase() + (e.id ? "#" + e.id : "") + (typeof e.className === "string" && e.className.trim() ? "." + e.className.trim().split(/\\s+/).join(".") : "");
      var clipped = false;
      for (var p = e.parentElement; p && p !== document.body; p = p.parentElement) {
        if (getComputedStyle(p).overflowX !== "visible") { clipped = true; break; }
      }
      var m = [cs.marginLeft, cs.marginRight, cs.paddingLeft, cs.paddingRight].map(function (v) { return Math.round(parseFloat(v) || 0); });
      rows.push([i, name, Math.round(r.left * 10) / 10, Math.round(r.right * 10) / 10, cs.textAlign, clipped, inline, m]);
    }
    var pre = document.createElement("pre"); pre.id = "ivn-probe";
    pre.textContent = JSON.stringify({w: root.clientWidth, sw: root.scrollWidth, rows: rows});
    document.body.appendChild(pre);
  }
  window.addEventListener("load", function () { setTimeout(run, 200); });
})();</script>"""


def render(page, rtl, size, tmp):
    text = read(page)
    base = '<base href="file://%s/">' % os.path.dirname(os.path.abspath(page))
    if re.search(r"<head\b", text, re.I):
        text = re.sub(r"(<head\b[^>]*>)", lambda m: m.group(1) + base, text, count=1, flags=re.I)
    else:
        text = base + text
    probe = PROBE % ("true" if rtl else "false")
    at = text.lower().rfind("</body>")
    text = text + probe if at < 0 else text[:at] + probe + text[at:]
    copy = os.path.join(tmp, "probe_%s.html" % ("rtl" if rtl else "ltr"))
    with open(copy, "w", encoding="utf-8") as f:
        f.write(text)
    out = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                          "--virtual-time-budget=3000", "--window-size=" + size, "--dump-dom", "file://" + copy],
                         capture_output=True, text=True, timeout=60).stdout
    m = re.search(r'<pre id="ivn-probe">(.*?)</pre>', out, re.S)
    return json.loads(html.unescape(m.group(1))) if m else None


def check_rtl(pages):
    if not os.access(CHROME, os.X_OK):
        print("SKIP Chrome not found at %s (set CHROME=...)" % CHROME)
        return 3
    size, bad = os.environ.get("IVN_PAGE_SIZE", "1280,900"), 0
    for page in pages:
        with tempfile.TemporaryDirectory() as tmp:
            ltr, rtl = render(page, False, size, tmp), render(page, True, size, tmp)
        if not ltr or not rtl:
            bad += 1
            print("FAIL %s: the page did not finish rendering in headless Chrome (no layout was read)" % show(page))
            continue
        found = []
        if rtl["sw"] > rtl["w"] + 1:
            found.append("the page scrolls sideways in right-to-left (content %dpx wide in a %dpx window)" % (rtl["sw"], rtl["w"]))
        past = [r[1] for r in rtl["rows"] if not r[5] and (r[2] < -1 or r[3] > rtl["w"] + 1)]
        if past:
            found.append("%d box(es) run past the window's edge in right-to-left (the part past the left edge cannot be scrolled to): %s"
                         % (len(past), ", ".join(past[:3])))
        width, by_i, off = ltr["w"], {r[0]: r for r in rtl["rows"]}, []
        phys = []
        for i, name, left, right, _, _, inline, m in ltr["rows"]:
            row = by_i.get(i)
            if row is None:
                continue
            if m[0] != row[7][1] or m[1] != row[7][0] or m[2] != row[7][3] or m[3] != row[7][2]:
                phys.append("%s has margin-left/right %d/%d and padding-left/right %d/%d left-to-right, %d/%d and %d/%d right-to-left (they should swap sides)"
                            % (name, m[0], m[1], m[2], m[3], row[7][0], row[7][1], row[7][2], row[7][3]))
            if not inline and (abs(row[2] - (width - right)) > 2 or abs(row[3] - (width - left)) > 2):
                off.append("%s sits at %.0f–%.0f left-to-right and %.0f–%.0f right-to-left (a mirror puts it at %.0f–%.0f)"
                           % (name, left, right, row[2], row[3], width - right, width - left))
        if off:
            found.append("%d box(es) do not mirror — a left or right set in physical terms (margin-left, float, left:, "
                         "padding-right) instead of the logical ones; first: %s" % (len(off), "; ".join(off[:3])))
        if phys:
            found.append("%d element(s) keep a physical margin or padding in right-to-left (margin-left, padding-right, …) instead of the logical ones; first: %s"
                         % (len(phys), "; ".join(phys[:3])))
        pinned = sorted({r[1] for r in rtl["rows"] if r[4] in ("left", "right")})
        if pinned:
            found.append("text pinned to a physical side (text-align left or right) on: %s — use start or end" % ", ".join(pinned[:4]))
        for f in found:
            bad += 1
            print("FAIL %s: %s" % (show(page), f))
    print(("PASS" if not bad else "FAIL") + " right-to-left render — %d page(s), %s window: %s" % (len(pages), size, ", ".join(map(show, pages))))
    return 1 if bad else 0


if __name__ == "__main__":
    checks = {"version": check_version, "contrast": check_contrast, "rtl": check_rtl}
    if len(sys.argv) < 3 or sys.argv[1] not in checks:
        sys.exit(__doc__)
    sys.exit(checks[sys.argv[1]]([os.path.abspath(p) for p in sys.argv[2:]]))
