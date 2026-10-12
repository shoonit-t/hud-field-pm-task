#!/usr/bin/env bash
# Part 2b: send traffic to the endpoints under study, so there are traces to compare.
#
#   scripts/part2b/traffic.sh trades [count] [label]   GET /api/market/stocks/:symbol/trades
#   scripts/part2b/traffic.sh summary [count] [label]  GET /api/market/stocks/:symbol/trades/summary
#   scripts/part2b/traffic.sh orders [label]           POST /api/orders, simultaneous per account
#
# `trades` and `summary` send requests one after another, rotating over ten stocks. One of
# the ten, AAPL, has far more trades than the rest.
#
# `orders` sends 40 one-share buys in five rounds. Each round takes two accounts and
# places four orders on each at the same moment, so orders on one account meet at that
# account's row lock. Eight in flight is deliberate: the API has ten database
# connections, and a larger burst queues for a connection before it ever reaches the
# lock, which is a different problem from the one this is here to show. Each account
# places four orders in total, well under the ten a minute the fraud service allows.
#
# `mixed` is the same order, sent two ways, with no change to the service. Five rounds of
# seven orders placed one at a time on accounts nobody else is using; after rounds two
# and four, six orders placed at the same moment on a single account. 47 orders: 35
# spaced out, 12 colliding. Six, because the eighth in a queue of eight waits close to
# the 250 ms statement limit the order flow sets, and is cancelled and retried.
#
#   scripts/part2b/traffic.sh mixed [label]
#
# Every request carries `User-Agent: part2b-<label>` (label defaults to the case name),
# so one run can be picked out in Jaeger with the tag `http.user_agent=part2b-<label>`.
#
# Prints one line per request (status and total time) and a summary. Run it from Git Bash.
set -euo pipefail

API="${API:-http://localhost:4000}"
CASE="${1:-}"

# The load generator's accounts.
USERS=(l.zhang m.rossi n.haddad j.tanaka y.petrov r.dubois k.novak a.okafor e.olsen c.mendes)
SYMBOLS=(NXPI AAPL MSFT NVDA AMZN JPM XOM KO PFE CSCO)

login() {
  curl -s -X POST "$API/api/auth/login" -H 'content-type: application/json' \
    -d "{\"username\":\"$1\",\"password\":\"part2b\"}" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p'
}

# status and seconds for one GET, e.g. "200 0.004"
timed_get() {
  curl -s -o /dev/null -w '%{http_code} %{time_total}' -A "$AGENT" \
    -H "authorization: Bearer $2" "$API$1"
}

# status and seconds for a one-share market buy
timed_buy() {
  curl -s -o /dev/null -w '%{http_code} %{time_total}' -A "$AGENT" -X POST "$API/api/orders" \
    -H "authorization: Bearer $2" -H 'content-type: application/json' \
    -d "{\"symbol\":\"$1\",\"side\":\"BUY\",\"quantity\":1}"
}

to_ms() { awk -v s="$1" 'BEGIN { printf "%d", s * 1000 }'; }

case "$CASE" in
  trades|summary|orders|mixed) ;;
  *) echo "usage: $0 trades|summary [count] [label]  |  $0 orders|mixed [label]" >&2; exit 2 ;;
esac

case "$CASE" in
  orders|mixed) AGENT="part2b-${2:-$CASE}" ;;
  *) AGENT="part2b-${3:-$CASE}" ;;
esac

declare -a TOKENS
for user in "${USERS[@]}"; do TOKENS+=("$(login "$user")"); done

if [[ "$CASE" == mixed ]]; then
  ROUNDS=5
  SPACED_PER_ROUND=7
  BURST=6
  results="$(mktemp)"
  trap 'rm -f "$results"' EXIT

  spaced=0
  bursts=0
  for ((round = 1; round <= ROUNDS; round++)); do
    # One at a time, rotating over the second five accounts.
    for ((s = 0; s < SPACED_PER_ROUND; s++)); do
      u=$((5 + spaced % 5))
      echo "spaced ${USERS[$u]} $(timed_buy "${SYMBOLS[$u]}" "${TOKENS[$u]}")" >>"$results"
      spaced=$((spaced + 1))
    done

    # All at once, on one of the first five accounts.
    if ((round == 2 || round == 4)); then
      u=$bursts
      for ((b = 0; b < BURST; b++)); do
        echo "burst ${USERS[$u]} $(timed_buy "${SYMBOLS[$u]}" "${TOKENS[$u]}")" >>"$results" &
      done
      wait
      bursts=$((bursts + 1))
    fi
  done

  while read -r kind user status seconds; do
    printf '%-6s  %-10s  %s  %5d ms\n' "$kind" "$user" "$status" "$(to_ms "$seconds")"
  done <"$results"
  echo "---"
  awk '{ ms = $4 * 1000; n[$1]++; total[$1] += ms; if (ms > max[$1]) max[$1] = ms; codes[$3]++ }
       END { for (k in n) printf "%s: %d orders, average %d ms, slowest %d ms\n", k, n[k], total[k] / n[k], max[k];
             printf "statuses:"; for (c in codes) printf " %s x%d", c, codes[c]; print "" }' "$results"
  exit 0
fi

if [[ "$CASE" == orders ]]; then
  ACCOUNTS_PER_ROUND=2
  ORDERS_PER_ACCOUNT=4
  results="$(mktemp)"
  trap 'rm -f "$results"' EXIT

  for ((first = 0; first < ${#USERS[@]}; first += ACCOUNTS_PER_ROUND)); do
    # Every order in the round is started before any is waited for.
    for ((u = first; u < first + ACCOUNTS_PER_ROUND; u++)); do
      for ((b = 0; b < ORDERS_PER_ACCOUNT; b++)); do
        echo "${USERS[$u]} $(timed_buy "${SYMBOLS[$u]}" "${TOKENS[$u]}")" >>"$results" &
      done
    done
    wait
  done

  sort "$results" | while read -r user status seconds; do
    printf '%-10s  %s  %5d ms\n' "$user" "$status" "$(to_ms "$seconds")"
  done
  echo "---"
  awk '{ ms = $3 * 1000; total += ms; if (ms > max) max = ms; n++; codes[$2]++ }
       END { printf "%d orders, %d at once per account: average %d ms, slowest %d ms; statuses:", n, per, total / n, max;
             for (c in codes) printf " %s x%d", c, codes[c]; print "" }' per="$ORDERS_PER_ACCOUNT" "$results"
  exit 0
fi

COUNT="${2:-50}"
total_ms=0
max_ms=0
for ((i = 0; i < COUNT; i++)); do
  token="${TOKENS[$((i % ${#TOKENS[@]}))]}"
  path="/api/market/stocks/${SYMBOLS[$((i % ${#SYMBOLS[@]}))]}/trades"
  [[ "$CASE" == summary ]] && path="$path/summary"

  read -r status seconds <<<"$(timed_get "$path" "$token")"
  ms=$(to_ms "$seconds")
  total_ms=$((total_ms + ms))
  ((ms > max_ms)) && max_ms=$ms
  printf '%3d  %s  %5d ms  %s\n' "$((i + 1))" "$status" "$ms" "$path"
done

echo "---"
echo "$COUNT requests to $CASE: average $((total_ms / COUNT)) ms, slowest $max_ms ms"
