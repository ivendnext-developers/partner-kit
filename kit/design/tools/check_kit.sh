#!/bin/bash
# ivn-kit 0.1.0 · the kit's exit check. Run from anywhere:
#   tools/check_kit.sh                 checks the kit and its three templates
#   tools/check_kit.sh page.html ...   runs checks (b), (b2), (b3) and (e) on those partner pages instead
# (a) no licensed or third-party UI library, and nothing loaded from a CDN or remote URL
# (b) tokens only: no colour literal or font in a page — colours come from --ivn-* variables
# (b2) the kit version a page loads: its own copy, the same version as this kit (tools/check_page.py)
# (b3) contrast on the page's own text/background pairs, light and dark (tools/check_page.py)
# (c) contrast numbers for both themes (tools/contrast.py)
# (d) ivn-kit.js behaviour test in headless Chrome (skipped when Chrome is not installed)
# (e) the page rendered right-to-left in headless Chrome: boxes mirror, no sideways scroll, no text pinned left/right
# Exit 0 = all pass. Exit 1 = something failed (the output says what).
set -u
KIT="$(cd "$(dirname "$0")/.." && pwd)"
ARGS=(); for a in "$@"; do ARGS+=("$(cd "$(dirname "$a")" && pwd)/$(basename "$a")"); done   # pages are named from where you stand
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
FAILS=0
cd "$KIT" || exit 1
echo "ivn-kit check · $(grep -o 'ivn-kit [0-9.]*' ivn-kit.css | head -1) · $(date '+%Y-%m-%d %H:%M')"

echo; echo "== (a) licensed libraries and remote loads =="
LICENSED='smart\.|smart-element|jqwidgets|kendo|syncfusion|devexpress|ag-grid-enterprise|handsontable|fontawesome-pro'
FILES=$(find . -type f ! -path './tools/check_kit.sh' | sort)
echo "files scanned: $(echo "$FILES" | wc -l | tr -d ' ')"
HITS=$(echo "$FILES" | xargs grep -n -i -E "$LICENSED" 2>/dev/null)
if [ -n "$HITS" ]; then echo "FAIL licensed library reference:"; echo "$HITS"; FAILS=$((FAILS+1)); else echo "PASS no licensed library name ($LICENSED)"; fi
LIBFILES=$(find . -type f \( -iname '*smart*' -o -iname '*.min.js' -o -iname '*.min.css' -o -iname '*.woff*' -o -iname '*.ttf' \))
if [ -n "$LIBFILES" ]; then echo "FAIL third-party asset files: $LIBFILES"; FAILS=$((FAILS+1)); else echo "PASS no vendored library, minified bundle or font file"; fi
CODE=$(find . -type f \( -name '*.html' -o -name '*.css' -o -name '*.js' \) | sort)
REMOTE=$(echo "$CODE" | xargs grep -n -i -E 'https?://|(src|href)[[:space:]]*=[[:space:]]*["'"'"']?//|@import|url\([[:space:]]*["'"'"']?//' 2>/dev/null)
if [ -n "$REMOTE" ]; then echo "FAIL remote URL in kit code:"; echo "$REMOTE"; FAILS=$((FAILS+1)); else echo "PASS nothing loaded from a CDN or remote URL ($(echo "$CODE" | wc -l | tr -d ' ') html/css/js files)"; fi
NET=$(grep -n -E 'fetch\(|XMLHttpRequest|WebSocket|sendBeacon|EventSource|importScripts' ivn-kit.js)
if [ -n "$NET" ]; then echo "FAIL ivn-kit.js makes network calls:"; echo "$NET"; FAILS=$((FAILS+1)); else echo "PASS ivn-kit.js has no network call"; fi

echo; echo "== (b) tokens only (no colour literal or font outside the kit) =="
PAGES=(${ARGS[@]+"${ARGS[@]}"}); [ ${#PAGES[@]} -eq 0 ] && PAGES=(templates/*.html)
python3 - "${PAGES[@]}" <<'PY' || FAILS=$((FAILS+1))
import re, sys
COLOUR_PROPS = r"(?<![\w-])(color|background|background-color|border|border-[a-z-]*color|border-(?:top|bottom|left|right|block|inline)(?:-start|-end)?|outline|outline-color|fill|stroke|box-shadow|text-shadow|caret-color|accent-color)\s*:\s*([^;\"'}]+)"
OK_VALUE = re.compile(r"^(var\(--ivn-[a-z0-9-]+\)|currentcolor|transparent|inherit|none|0)$", re.I)
rules = [
    ("hex colour", re.compile(r"#(?:[0-9a-f]{8}|[0-9a-f]{6}|[0-9a-f]{4}|[0-9a-f]{3})(?![\w-])", re.I)),
    ("rgb()/hsl() colour", re.compile(r"\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(", re.I)),
    ("font family", re.compile(r"font-family|(?<![\w-])font\s*:", re.I)),
    ("svg colour attribute", re.compile(r"\b(?:fill|stroke|color|stop-color)\s*=\s*[\"'](?!none[\"']|currentColor[\"'])", re.I)),
]
bad = 0
for path in sys.argv[1:]:
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        for name, rx in rules:
            if rx.search(line):
                bad += 1; print("FAIL %s:%d %s: %s" % (path, n, name, line.strip()[:120]))
        for prop, value in re.findall(COLOUR_PROPS, line, re.I):
            for part in value.split():
                if re.match(r"^[a-z]+$", part, re.I) and not OK_VALUE.match(part) and part.lower() not in ("solid", "dashed", "dotted", "double", "inset"):
                    bad += 1; print("FAIL %s:%d named colour in %s: %s" % (path, n, prop, part))
print(("PASS" if not bad else "FAIL") + " tokens only — %d page(s): %s" % (len(sys.argv) - 1, ", ".join(sys.argv[1:])))
sys.exit(1 if bad else 0)
PY

echo; echo "== (b2) the kit version a page loads =="
python3 tools/check_page.py version "${PAGES[@]}" || FAILS=$((FAILS+1))

echo; echo "== (b3) contrast on the page's own colour pairs =="
python3 tools/check_page.py contrast "${PAGES[@]}" || FAILS=$((FAILS+1))

echo; echo "== (c) contrast =="
python3 tools/contrast.py || FAILS=$((FAILS+1))

echo; echo "== (d) ivn-kit.js behaviour (headless Chrome) =="
if [ -x "$CHROME" ]; then
  OUT=$("$CHROME" --headless=new --disable-gpu --virtual-time-budget=5000 --dump-dom "file://$KIT/tools/test_kit_js.html" 2>/dev/null \
        | sed -n '/<pre id="out">/,/<\/pre>/p' | sed -e 's/<[^>]*>//g' -e 's/&lt;/</g' -e 's/&gt;/>/g')
  echo "$OUT" | grep -E '^(FAIL|RESULT)'
  echo "$OUT" | grep -q '^RESULT: PASS' || FAILS=$((FAILS+1))
else
  echo "SKIP Chrome not found at $CHROME (set CHROME=...)"; SKIPPED=1
fi

echo; echo "== (e) right-to-left render of the pages (headless Chrome) =="
python3 tools/check_page.py rtl "${PAGES[@]}"; RC=$?
[ "$RC" -eq 1 ] && FAILS=$((FAILS+1)); [ "$RC" -eq 3 ] && SKIPPED=1

echo; echo "== kit size =="
wc -l ivn-kit.css ivn-kit.js | sed 's/^/  /'
echo; if [ "$FAILS" -ne 0 ]; then echo "CHECK: FAIL ($FAILS section(s))"
elif [ "${SKIPPED:-0}" -eq 1 ]; then echo "CHECK: INCOMPLETE (the behaviour section was skipped: no Chrome)"; exit 3
else echo "CHECK: PASS"; fi
exit $([ "$FAILS" -eq 0 ] && echo 0 || echo 1)
