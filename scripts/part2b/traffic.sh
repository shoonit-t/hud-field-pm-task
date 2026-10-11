#!/usr/bin/env bash
# Part 2b: send traffic to the endpoints under study, so there are traces to compare.
#
#   scripts/part2b/traffic.sh trades [count]   GET /api/market/stocks/:symbol/trades
#   scripts/part2b/traffic.sh lots   [count]   GET /api/portfolio/lots
#
# Prints one line per request (status and total time) and a summary. Run it from Git Bash.
set -euo pipefail

API="${API:-http://localhost:4000}"
CASE="${1:-}"
COUNT="${2:-50}"

# The load generator's accounts: each holds 28 to 43 positions.
USERS=(l.zhang m.rossi n.haddad j.tanaka y.petrov r.dubois k.novak a.okafor e.olsen c.mendes)
SYMBOLS=(NXPI AAPL MSFT NVDA AMZN JPM XOM KO PFE CSCO)

login() {
  curl -s -X POST "$API/api/auth/login" -H 'content-type: application/json' \
    -d "{\"username\":\"$1\",\"password\":\"part2b\"}" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p'
}

# status and seconds for one GET, e.g. "200 0.004"
timed_get() {
  curl -s -o /dev/null -w '%{http_code} %{time_total}' -H "authorization: Bearer $2" "$API$1"
}

case "$CASE" in
  trades|lots) ;;
  *) echo "usage: $0 trades|lots [count]" >&2; exit 2 ;;
esac

declare -a TOKENS
for user in "${USERS[@]}"; do TOKENS+=("$(login "$user")"); done

total_ms=0
max_ms=0
for ((i = 0; i < COUNT; i++)); do
  token="${TOKENS[$((i % ${#TOKENS[@]}))]}"
  if [[ "$CASE" == trades ]]; then
    path="/api/market/stocks/${SYMBOLS[$((i % ${#SYMBOLS[@]}))]}/trades"
  else
    path="/api/portfolio/lots"
  fi

  read -r status seconds <<<"$(timed_get "$path" "$token")"
  ms=$(awk -v s="$seconds" 'BEGIN { printf "%d", s * 1000 }')
  total_ms=$((total_ms + ms))
  ((ms > max_ms)) && max_ms=$ms
  printf '%3d  %s  %5d ms  %s\n' "$((i + 1))" "$status" "$ms" "$path"
done

echo "---"
echo "$COUNT requests to $CASE: average $((total_ms / COUNT)) ms, slowest $max_ms ms"
