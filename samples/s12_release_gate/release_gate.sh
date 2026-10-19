#!/usr/bin/env bash
# release_gate.sh — a customer's release gate for their own changes to a shop. Red or green, one exit code.
#
#   bash release_gate.sh --baskets baskets.json [--app path/to/your_app] [--manifest your_manifest.json] [--record]
#
# It runs, against the STAGING shop, in this order, and stops nothing early (you see every failure at once):
#   1. SELF-CHECK  the self-check on your app folder (tools/selfcheck) — reads your files, runs nothing. Skipped if you ship no app.
#   2. BASKETS     your RECORDED baskets (the shape of baskets.json beside this script) rung through the till's own calls on the
#                  staging shop: for each, the till's PREVIEW, the BOOKED sale and the back-office invoice it is merged into — the money
#                  kit's check. A basket is RED if its preview and its booking differ, OR if its booked totals differ from the answer
#                  you recorded. One line per basket: the figure you expected, the figure booked, the figure previewed.
#   3. POS DAYS    nothing left open: every till day the gate opened must be closed.
# Exit 0 only if all three are green. Exit 1 if any is red. Exit 2 if the gate could not run (nothing is proven either way).
#
# ⚠ One gate at a time on a staging box: the console command shares one output file in the bench (our own test bench's console
# command deletes it before every run, and a lock serialises runs; a console command of your own must do the same — the gate reads
# only the record named for THIS run, so it cannot read an old one, but two runs overlapping could overwrite each other's).
# ⚠ Run it on a STAGING shop, never a live one: it books real sales (simulated card) and closes real till days there.
# What you may need to change for your own staging box is the block marked HERE below — nothing else.
# --record is for the ONE run that records your baskets' answers (record_expect.py); without it every basket MUST carry its recorded
# answer, so a basket whose answer is missing or misspelled can never pass silently.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
KIT_ROOT="${GATE_KIT_ROOT:-$(cd "$HERE/../.." && pwd)}"          # the kit's folder (tools/…, samples/…)

# ── HERE: how this script reaches the staging shop's console ────────────────────────────────────────────────────────────────────
[ -n "${GATE_CONSOLE:-}" ] && [ -n "${GATE_RUNS:-}" ] && [ -n "${GATE_CONTAINER:-}" ] \
  || { echo "GATE set GATE_CONSOLE, GATE_RUNS and GATE_CONTAINER (your staging box): nothing is proven"; exit 2; }
# GATE_CONSOLE   the command that runs a console script in the staging shop: <script> <out> <steps…>
# GATE_RUNS      the folder where that command leaves the run record <out>.json
# GATE_CONTAINER the staging shop's container
GATE_KIT_SCRIPT="${GATE_KIT_SCRIPT:-tools/moneykit/kit.py}"     # the money kit (this kit's tools/moneykit/), as the console command names it
GATE_KIT_SETTINGS="${GATE_KIT_SETTINGS:-}"                       # the kit's settings, ';' between them (tools/moneykit/README.md):
#   kit_dir:<folder in the bench>  needed when the console runs the script's text (no __file__ to find till.py by)
#   shop:<file in the bench>       the cashier, device, POS profile and terminal (default: shop.json beside till.py)
#   record:<file in the bench>     where the kit writes its record (default: pp_out.json in the console user's home) —
#                                  GATE_CONSOLE must leave that record in GATE_RUNS as <out>.json
GATE_PY="${GATE_PY:-python3}"
GATE_PUT="${GATE_PUT:-docker cp}"                                # <local file> <container>:<path in the bench> — puts your baskets file into the staging bench
GATE_RM="${GATE_RM:-docker exec $GATE_CONTAINER rm -f}"          # <path in the bench> — removes it again
GATE_BENCH_TMP="${GATE_BENCH_TMP:-/home/frappe}"                 # a folder in the bench the console can read (the bench user's home)
# ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

BASKETS=""; APP=""; MANIFEST=""; RECORD=0
while [ $# -gt 0 ]; do
  case "$1" in
    --record) RECORD=1; shift; continue ;;
    --baskets|--app|--manifest) [ $# -ge 2 ] || { echo "GATE $1 needs a value"; exit 2; } ;;
  esac
  case "$1" in
    --baskets) BASKETS="${2:-}"; shift 2 ;;
    --app) APP="${2:-}"; shift 2 ;;
    --manifest) MANIFEST="${2:-}"; shift 2 ;;
    *) echo "GATE usage: release_gate.sh --baskets FILE [--app DIR] [--manifest FILE]"; exit 2 ;;
  esac
done
[ -r "$BASKETS" ] || { echo "GATE cannot read the baskets file '$BASKETS'"; exit 2; }
SETTINGS=()
[ -z "$GATE_KIT_SETTINGS" ] || IFS=';' read -r -a SETTINGS <<< "$GATE_KIT_SETTINGS"
for s in ${SETTINGS[@]+"${SETTINGS[@]}"}; do   # only the three settings the gate's steps read: never a step that rings or seeds
  case "$s" in kit_dir:?*|shop:?*|record:?*) ;; *) echo "GATE GATE_KIT_SETTINGS takes only kit_dir:, shop: and record: ('$s')"; exit 2 ;; esac
done
"$GATE_PY" -c "import json,sys; b=json.load(open(sys.argv[1]))['baskets']; assert b and all(x.get('name') and x.get('lines') for x in b)" "$BASKETS" 2>/dev/null \
  || { echo "GATE the baskets file is not in the recorded-baskets shape (a 'baskets' list, each with a name and lines)"; exit 2; }
if [ "$RECORD" -eq 0 ]; then
  "$GATE_PY" -c "import json,sys; b=json.load(open(sys.argv[1]))['baskets']; bad=[x['name'] for x in b if not isinstance((x.get('expect') or {}).get('grand_total'), (int, float))]; print('; '.join(bad)); sys.exit(1 if bad else 0)" "$BASKETS" > "${TMPDIR:-/tmp}/gate_noexpect.$$" 2>/dev/null \
    || { echo "GATE these baskets carry no recorded answer (expect.grand_total), so the gate would check nothing for them: $(cat "${TMPDIR:-/tmp}/gate_noexpect.$$"). Record them first (--record, then record_expect.py)"; rm -f "${TMPDIR:-/tmp}/gate_noexpect.$$"; exit 2; }
  rm -f "${TMPDIR:-/tmp}/gate_noexpect.$$"
fi

RC=0
echo "GATE 1/3 self-check"
if [ -n "$APP" ]; then
  args=("$APP"); [ -n "$MANIFEST" ] && args+=(--manifest "$MANIFEST")
  out="$("$GATE_PY" "$KIT_ROOT/tools/selfcheck/selfcheck.py" "${args[@]}" 2>&1)"; src=$?
  printf '%s\n' "$out" | sed 's/^/GATE   /'
  if [ "$src" -eq 0 ]; then echo "GATE self-check GREEN"; else echo "GATE self-check RED (exit $src)"; RC=1; fi
else
  echo "GATE self-check SKIPPED (no --app: you ship no code into the shop)"
fi

echo "GATE 2/3 baskets"
ID="gate_$(date +%s)_$$"
INBENCH="$GATE_BENCH_TMP/pp_$ID.baskets.json"                      # this run's own file: two jobs on one box never share it
$GATE_PUT "$BASKETS" "$GATE_CONTAINER:$INBENCH" >/dev/null 2>&1 || { echo "GATE could not copy the baskets into the staging bench ($GATE_CONTAINER)"; exit 2; }
$GATE_CONSOLE "$GATE_KIT_SCRIPT" "$ID" ${SETTINGS[@]+"${SETTINGS[@]}"} "gate_stock:$INBENCH" "gate:$INBENCH" pos_day_check > "$GATE_RUNS/$ID.console.log" 2>&1
$GATE_RM "$INBENCH" >/dev/null 2>&1 || true
REC="$GATE_RUNS/$ID.json"
[ -r "$REC" ] || { echo "GATE the staging shop's console left no record ($REC): nothing is proven"; tail -5 "$GATE_RUNS/$ID.console.log" | sed 's/^/GATE   /'; exit 2; }
"$GATE_PY" - "$REC" <<'PY'
import json, sys
rec = json.load(open(sys.argv[1]))
if not rec.get("ok") or not rec.get("gate"):          # a step that failed, or no basket rung at all: nothing is proven
    print("GATE the staging shop's console did not ring the baskets:", rec.get("error") or "no basket was rung"); sys.exit(2)
red = 0
for r in rec.get("gate", []):
    exp, bk, pv = (r.get("expect") or {}).get("grand_total"), (r.get("booked") or {}).get("grand_total"), (r.get("preview") or {}).get("grand_total")
    f = lambda v: "-" if v is None else f"{float(v):,.2f}"
    ok = r["state"] == "matched"
    red += not ok
    print(f"GATE   {r['id']} {'OK ' if ok else 'RED'} \"{r['name']}\"  expected {f(exp)}  booked {f(bk)}  preview {f(pv)}" +
          ("" if ok else f"  <- {r['state']}: " + "; ".join(r.get("detail") or [])[:300]))
print(f"GATE baskets {'GREEN' if red == 0 and rec.get('gate_green') else 'RED'}: {len(rec.get('gate', [])) - red} of {len(rec.get('gate', []))} matched")
sys.exit(1 if red or not rec.get("gate_green") else 0)
PY
BRC=$?
[ "$BRC" -eq 2 ] && { echo "GATE RESULT NOT PROVEN — the gate could not run (this is not a pass)"; exit 2; }
[ "$BRC" -eq 0 ] || RC=1

echo "GATE 3/3 till days"
OPEN="$("$GATE_PY" -c "import json,sys; d=json.load(open(sys.argv[1])).get('open_days'); print(len(d) if isinstance(d,list) else 'unknown')" "$REC")"
if [ "$OPEN" = "0" ]; then echo "GATE open POS days: 0 GREEN"; else echo "GATE open POS days: $OPEN RED (a day the gate or an earlier run left open poisons that cashier for every later test)"; RC=1; fi

[ "$RC" -eq 0 ] && echo "GATE RESULT GREEN — safe to release" || echo "GATE RESULT RED — do not release"
exit "$RC"
