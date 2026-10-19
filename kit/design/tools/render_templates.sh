#!/bin/bash
# ivn-kit 0.1.0 · render every template light, dark and right-to-left to PNG with headless Chrome.
# Usage: tools/render_templates.sh <out-dir>     (local files only; nothing is fetched)
set -u
KIT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:?usage: render_templates.sh <out-dir>}"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
mkdir -p "$OUT"
for t in desk_page till_sheet portal; do
  size="1280,900"; [ "$t" = till_sheet ] && size="420,800"
  for look in light dark rtl; do
    case $look in light) qs="?theme=light";; dark) qs="?theme=dark";; rtl) qs="?theme=light&dir=rtl";; esac
    url="file://$KIT/templates/$t.html$qs"
    # Headless Chrome will not go below 500px wide: the till sheet goes through a 420x800 frame.
    [ "$t" = till_sheet ] && url="file://$KIT/tools/frame.html?t=till_sheet&w=420&h=800&${qs#?}"
    "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
      --virtual-time-budget=2000 --screenshot="$OUT/${t}_${look}.png" --window-size="$size" "$url" >/dev/null 2>&1
    echo "rendered ${t}_${look}.png ($size)"
  done
done
