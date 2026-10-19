#!/usr/bin/env bash
# run.sh — the language-neutral proof: every call the samples make, with curl and jq alone (no client library).
#
#   BASE=https://<your-sandbox-site> KEY=<api key> SECRET=<api secret> bash api/collection/run.sh
#
# Each NN_*.http file IS the request: its first non-comment line is "METHOD URL", then headers, then a blank
# line and an optional JSON body. {{NAME}} is replaced by the environment variable NAME. Two comment lines
# drive the check:
#   # expect: <status> [<jq expression that must be true>]     ($ENV.NAME reads a variable)
#   # capture: NAME=<jq expression>                            (the value is used by later files)
# Prints PASS/FAIL per file and exits non-zero on any FAIL. Secrets are never printed.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
: "${BASE:?set BASE}" "${KEY:?set KEY}" "${SECRET:?set SECRET}"
export BASE KEY SECRET RUN="${RUN:-$(date -u +%Y%m%d%H%M%S)}"
command -v jq >/dev/null || { echo "run.sh needs jq"; exit 2; }

subst() {  # replace every {{NAME}} with $NAME; an unset NAME is an error (a capture failed earlier)
  local s="$1" v
  for v in $(printf '%s' "$s" | grep -oE '\{\{[A-Z_0-9]+\}\}' | sort -u | tr -d '{}'); do
    [ -n "${!v+x}" ] || { echo "@@UNSET $v"; return 1; }
    s="${s//\{\{$v\}\}/${!v}}"
  done
  printf '%s' "$s"
}
urlencode_query() {  # encode each query value; the path's spaces become %20
  local url="$1" path query out="" kv k v
  path="${url%%\?*}"; path="${path// /%20}"
  [ "$url" = "${url#*\?}" ] && { printf '%s' "$path"; return; }
  query="${url#*\?}"
  IFS='&' read -ra kv <<< "$query"
  for p in "${kv[@]}"; do
    k="${p%%=*}"; v="${p#*=}"
    out="$out&$k=$(jq -rn --arg v "$v" '$v|@uri')"
  done
  printf '%s?%s' "$path" "${out#&}"
}

pass=0; fail=0; T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
for f in "$HERE"/[0-9][0-9]_*.http; do
  name="$(basename "$f" .http)"
  expect="$(sed -n 's/^# expect: *//p' "$f" | head -1)"; want="${expect%% *}"; check=""
  [ "$expect" != "$want" ] && check="${expect#* }"
  reqline="$(grep -v '^#' "$f" | sed -n '1p')"
  method="${reqline%% *}"; url="${reqline#* }"
  if ! url="$(subst "$url")"; then echo "FAIL $name — $url"; fail=$((fail+1)); continue; fi
  url="$(urlencode_query "$url")"
  args=(-s -m 60 -o "$T/body" -w '%{http_code}' -X "$method")
  body=""; inbody=0
  while IFS= read -r line; do
    if [ "$inbody" = 1 ]; then body="$body$line"$'\n'; continue; fi
    [ -z "$line" ] && { inbody=1; continue; }
    h="$(subst "$line")" || { echo "FAIL $name — header needs an unset variable"; fail=$((fail+1)); continue 2; }
    args+=(-H "$h")
  done < <(grep -v '^#' "$f" | sed '1d')
  if [ -n "$body" ]; then
    body="$(subst "$body")" || { echo "FAIL $name — body needs an unset variable"; fail=$((fail+1)); continue; }
    args+=(--data-binary "$body")
  fi
  code="$(curl "${args[@]}" "$url")"
  ok=1; why=""
  [ "$code" = "$want" ] || { ok=0; why="HTTP $code, want $want"; }
  if [ "$ok" = 1 ] && [ -n "$check" ]; then
    jq -e "$check" "$T/body" >/dev/null 2>&1 || { ok=0; why="check failed: $check"; }
  fi
  if [ "$ok" = 1 ]; then
    while IFS= read -r cap; do
      [ -n "$cap" ] || continue
      var="${cap%%=*}"; expr="${cap#*=}"
      val="$(jq -r "$expr // empty" "$T/body" 2>/dev/null)"
      [ -n "$val" ] || { ok=0; why="capture $var empty"; break; }
      export "$var=$val"
    done < <(sed -n 's/^# capture: *//p' "$f")
  fi
  if [ "$ok" = 1 ]; then
    pass=$((pass+1)); echo "PASS $name ($method $code)"
  else
    fail=$((fail+1)); echo "FAIL $name ($method) — $why"
    jq -c '{exc_type, _server_messages, exception} | with_entries(select(.value != null))' "$T/body" 2>/dev/null | cut -c1-400
  fi
done
echo "COLLECTION run=$RUN pass=$pass fail=$fail"
[ "$fail" = 0 ]
