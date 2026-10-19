#!/usr/bin/env python3
"""ivn-kit 0.1.0 · contrast check. Reads the token values straight out of ivn-kit.css (and the
sample tenant themes), works out WCAG 2.1 contrast for every text and control pairing the kit
draws, prints a table, and exits 1 if any pairing is under its floor.
Floors: 4.5:1 for text, 3:1 for focus rings and control boundaries (WCAG 1.4.3 / 1.4.11)."""
import json, os, re, sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
css = open(os.path.join(KIT, "ivn-kit.css")).read()

def block(selector_regex):
    m = re.search(selector_regex + r"\s*\{(.*?)\n\s*\}", css, re.S)
    if not m:
        sys.exit("contrast: block not found: " + selector_regex)
    body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    return {k: v.strip() for k, v in re.findall(r"(--ivn-[a-z0-9-]+)\s*:\s*([^;]+);", body)}

light = block(r"\n:root")
dark = block(r':root\[data-theme="dark"\]')
media = block(r':root:not\(\[data-theme="light"\]\)')

def rgba(v):
    v = v.strip()
    if v.startswith("#"):
        h = v[1:]
        if len(h) in (3, 4): h = "".join(c * 2 for c in h)
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)
    nums = [float(n) for n in re.findall(r"[\d.]+", v)]
    return (nums[0], nums[1], nums[2], nums[3] if len(nums) > 3 else 1.0)

def over(top, under):  # composite a translucent colour over an opaque one
    r, g, b, a = top
    return tuple(r * a + u * (1 - a) for r, u in zip((r, g, b), under[:3])) + (1.0,)

def lum(c):
    def ch(x):
        x = x / 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])

def ratio(fg, bg):
    a, b = sorted((lum(fg), lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)

# (what it is, foreground token, background token, floor). Backgrounds that are translucent
# are composited over --ivn-surface, which is where the kit draws them.
PAIRS = [
    ("body text on page", "--ivn-text", "--ivn-bg", 4.5),
    ("body text on card", "--ivn-text", "--ivn-surface", 4.5),
    ("text on table head / default button", "--ivn-text", "--ivn-surface-2", 4.5),
    ("text in a field", "--ivn-text", "--ivn-control-bg", 4.5),
    ("muted text on page", "--ivn-text-muted", "--ivn-bg", 4.5),
    ("muted text on card", "--ivn-text-muted", "--ivn-surface", 4.5),
    ("placeholder in a field", "--ivn-text-muted", "--ivn-control-bg", 4.5),
    ("link on card", "--ivn-link", "--ivn-surface", 4.5),
    ("link on page", "--ivn-link", "--ivn-bg", 4.5),
    ("active chip text", "--ivn-pill-blue-ink", "--ivn-primary-tint", 4.5),
    ("primary button label", "--ivn-on-primary", "--ivn-primary-strong", 4.5),
    ("danger button label", "--ivn-on-primary", "--ivn-danger", 4.5),
    ("error text on card", "--ivn-danger-text", "--ivn-surface", 4.5),
    ("text in error state", "--ivn-text", "--ivn-danger-tint", 4.5),
    ("toast text", "--ivn-surface", "--ivn-text", 4.5),
    ("pill grey", "--ivn-pill-grey-ink", "--ivn-pill-grey-bg", 4.5),
    ("pill blue", "--ivn-pill-blue-ink", "--ivn-pill-blue-bg", 4.5),
    ("pill green", "--ivn-pill-green-ink", "--ivn-pill-green-bg", 4.5),
    ("pill orange", "--ivn-pill-orange-ink", "--ivn-pill-orange-bg", 4.5),
    ("pill red", "--ivn-pill-red-ink", "--ivn-pill-red-bg", 4.5),
    ("focus ring on card", "--ivn-focus", "--ivn-surface", 3.0),
    ("focus ring on page", "--ivn-focus", "--ivn-bg", 3.0),
    ("toggle on (track) + checkbox", "--ivn-primary", "--ivn-surface", 3.0),
    ("toggle off (track)", "--ivn-text-muted", "--ivn-surface", 3.0),
    ("selected border", "--ivn-primary", "--ivn-surface", 3.0),
    ("toggle knob on its track", "--ivn-surface", "--ivn-primary", 3.0),
]
# Shown, not enforced: Desk itself draws these below 3:1 (parity, recorded as a known gap).
INFO = [
    ("field fill vs card (Desk look)", "--ivn-control-bg", "--ivn-surface"),
    ("field outline vs card", "--ivn-control-border", "--ivn-surface"),
    ("chip outline vs card", "--ivn-border-strong", "--ivn-surface"),
]

def resolve(tokens, name):
    v = tokens[name]
    if v == "transparent":
        return None
    c = rgba(v)
    return over(c, rgba(tokens["--ivn-surface"])) if c[3] < 1 else c

def run(label, tokens):
    fails = 0
    print("\n[%s]" % label)
    for what, fg, bg, floor in PAIRS:
        r = ratio(resolve(tokens, fg), resolve(tokens, bg))
        ok = r >= floor
        fails += not ok
        print("  %-5s %5.2f:1  (floor %.1f)  %-36s %s on %s" % ("PASS" if ok else "FAIL", r, floor, what, tokens[fg], tokens[bg]))
    for what, fg, bg in INFO:
        a = resolve(tokens, fg)
        r = ratio(a, resolve(tokens, bg)) if a else 1.0
        print("  info  %5.2f:1               %-36s %s on %s" % (r, what, tokens[fg], tokens[bg]))
    return fails

def main():
    fails = 0
    if dark != media:
        print("FAIL: the data-theme=\"dark\" block and the prefers-color-scheme block differ:",
              sorted(k for k in set(dark) | set(media) if dark.get(k) != media.get(k)))
        fails += 1
    else:
        print("dark blocks identical (data-theme=\"dark\" == prefers-color-scheme): yes")
    fails += run("light (kit default)", light)
    fails += run("dark (kit default)", dict(light, **dark))

    sample = open(os.path.join(KIT, "templates", "sample-theme.js")).read()
    for mode in ("light", "dark"):
        m = re.search(mode + r":\s*\{\s*mode:\s*\"" + mode + r"\",\s*vars:\s*(\{.*?\})\s*\}", sample, re.S)
        if m:
            over_vars = json.loads(m.group(1))
            base = dict(light, **(dark if mode == "dark" else {}))
            fails += run("%s + sample POS tenant theme" % mode, dict(base, **over_vars))

    print("\ncontrast: %s (%d failing pairings)" % ("PASS" if not fails else "FAIL", fails))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
