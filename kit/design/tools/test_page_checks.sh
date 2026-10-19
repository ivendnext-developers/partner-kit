#!/bin/bash
# ivn-kit 0.1.0 · proves the page checks can fail: builds one good page and a set of pages each with one planted defect
# in a temporary folder, runs tools/check_page.py (and, for one, the whole tools/check_kit.sh) and requires every
# planted page to fail with its named reason and the good page to pass. Nothing is written into the kit.
#   tools/test_page_checks.sh       exit 0 = every check passed and every planted defect was caught
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; KIT="$(dirname "$HERE")"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir -p "$T/page"; cp "$KIT/ivn-kit.css" "$KIT/ivn-kit.js" "$T/"
# a stale copy of the kit, as a partner who copied it long ago would still be loading
VER="$(grep -o 'ivn-kit [0-9][0-9.]*' "$KIT/ivn-kit.css" | head -1 | cut -d' ' -f2)"
sed "s/ivn-kit $VER/ivn-kit 0.0.9/" "$KIT/ivn-kit.css" > "$T/ivn-kit-old.css"

page() {   # page <name> <css href> <extra css> <body html>
  cat > "$T/page/$1.html" <<EOF
<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Fixture</title>
<link rel="stylesheet" href="$2"><script src="../ivn-kit.js"></script>
<style>$3</style></head><body class="ivn">
<main class="ivn-container ivn-stack">$4</main></body></html>
EOF
}
BODY='<h1 class="ivn-title">Claims</h1><div class="ivn-row"><div class="note">Open claims</div><div class="side">Filters</div></div>'
page good           ../ivn-kit.css '.note{color:var(--ivn-text);background:var(--ivn-surface);padding-inline:var(--ivn-s3)} .side{margin-inline-start:var(--ivn-s4)}' "$BODY"
page old_version    ../ivn-kit-old.css '' "$BODY"
page no_kit         '' ''  "$BODY"
page gone_kit       ../gone/ivn-kit.css '' "$BODY"
page remote_kit     https://cdn.example.test/ivn-kit.css '' "$BODY"
page low_contrast   ../ivn-kit.css '.note{color:var(--ivn-border);background:var(--ivn-surface)}' "$BODY"
page low_in_dark    ../ivn-kit.css '.note{color:var(--ivn-primary-strong);background:var(--ivn-bg)}' "$BODY"
page unknown_token  ../ivn-kit.css '.note{color:var(--ivn-texxt)}' "$BODY"
page not_mirrored   ../ivn-kit.css '.note{margin-left:80px;width:200px}' "$BODY"
page floats_left    ../ivn-kit.css '.side{float:left;width:240px}' '<h1 class="ivn-title">Claims</h1><div><div class="side">Filters</div><p>Open claims</p></div>'
page pinned_text    ../ivn-kit.css '.note{text-align:right}' "$BODY"
page scrolls_sideways ../ivn-kit.css '.note{min-width:1600px}' "$BODY"
page inline_margin  ../ivn-kit.css '.gap{margin-right:40px}' '<h1 class="ivn-title">Claims</h1><p><span class="gap">Icon</span>Open claims</p>'
page commented_link ../ivn-kit.css '' "$BODY"
sed -i.bak 's|<link rel="stylesheet" href="../ivn-kit.css">|<!-- <link rel="stylesheet" href="../ivn-kit.css"> -->|' "$T/page/commented_link.html"
page quoted_style   ../ivn-kit.css '' '<p style='"'"'color:var(--ivn-border);background:var(--ivn-surface)'"'"'>Open claims</p>'
page fine_buttons   ../ivn-kit.css '.go{background:var(--ivn-primary-strong)} .go span{color:var(--ivn-on-primary)} .clear{background:var(--ivn-control-border)} .clear2{color:var(--ivn-text);background:var(--ivn-surface)}' '<h1 class="ivn-title">Claims</h1><button class="go"><span>Save</span></button><i class="clear clear2">x</i>'
page ltr_island     ../ivn-kit.css '.keys{display:flex;gap:8px}.keys b{margin-left:30px}' '<h1 class="ivn-title">Claims</h1><div dir="ltr" class="keys"><b>1</b><b>2</b><b>3</b></div>'

FAILS=0
expect() {   # expect <check> <page> <exit> <text the output must carry>
  local out rc; out=$(python3 "$HERE/check_page.py" "$1" "$T/page/$2.html" 2>&1); rc=$?
  if [ "$rc" -eq "$3" ] && ! echo "$out" | grep -q "Traceback" && { [ -z "$4" ] || echo "$out" | grep -q -F -- "$4"; }; then   # a crash is never a refusal
    echo "ok    $1 · $2 → exit $rc${4:+ · \"$4\"}"
  else echo "BAD   $1 · $2 → exit $rc (wanted $3${4:+ with \"$4\"})"; echo "$out" | sed 's/^/        /'; FAILS=$((FAILS+1)); fi
}
echo "== the good page passes every page check =="
for c in version contrast rtl; do expect $c good 0 "PASS"; done
echo "== pages that are right and must not be refused =="
for c in version contrast rtl; do expect $c fine_buttons 0 "PASS"; done
expect rtl ltr_island 0 "PASS"
echo "== the kit version a page loads =="
expect version old_version 1 "kit version 0.0.9; this kit is $VER"
expect version no_kit      1 "loads no ivn-kit stylesheet"
expect version gone_kit    1 "is not a file"
expect version remote_kit  1 "from a remote address"
expect version commented_link 1 "loads no ivn-kit stylesheet"
echo "== contrast on the page's own pairs =="
expect contrast low_contrast  1 "under the 4.5:1 text floor"
expect contrast low_in_dark   1 "(dark)"
expect contrast unknown_token 1 "is not a kit token"
expect contrast quoted_style  1 "under the 4.5:1 text floor"
echo "== right-to-left =="
expect rtl not_mirrored     1 "do not mirror"
expect rtl floats_left      1 "do not mirror"
expect rtl inline_margin    1 "keep a physical margin or padding"
expect rtl pinned_text      1 "text pinned to a physical side"
expect rtl scrolls_sideways 1 "run past the window's edge"
echo "== the whole check refuses a planted page, and passes the good one =="
for p in good old_version low_contrast not_mirrored; do
  "$KIT/tools/check_kit.sh" "$T/page/$p.html" > "$T/out_$p.txt" 2>&1; rc=$?
  want=1; [ "$p" = good ] && want=0
  if [ "$rc" -eq "$want" ]; then echo "ok    check_kit.sh · $p → exit $rc · $(grep '^CHECK:' "$T/out_$p.txt")"
  else echo "BAD   check_kit.sh · $p → exit $rc (wanted $want)"; tail -15 "$T/out_$p.txt" | sed 's/^/        /'; FAILS=$((FAILS+1)); fi
done
echo; [ "$FAILS" -eq 0 ] && echo "PAGE CHECKS: every planted defect caught, good page passes" || echo "PAGE CHECKS: $FAILS failure(s)"
exit $([ "$FAILS" -eq 0 ] && echo 0 || echo 1)
