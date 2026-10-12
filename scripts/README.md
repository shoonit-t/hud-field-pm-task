# Assignment work: how to reproduce

Branch `part2b-db-slowness`. Everything here supports the presentation; this file is only the commands.

## What the branch adds

| Area | Change |
|---|---|
| `services/trading-api` | Two endpoints: `GET /api/market/stocks/:symbol/trades` (latest 50 trades) and `GET /api/market/stocks/:symbol/trades/summary` (six-month summary). Migration `011` adds the index the first one needs. The order flow is unchanged |
| `scripts/part2b` | Data loads, an index toggle, a traffic script, a Jaeger screenshot tool, a mock per-query page |
| `scripts/part3` | A test of the proposed SDK change, and the generator for the event-loop animation |

## Setup, once

```bash
docker compose up --build -d
docker compose exec -T postgres psql -U headsup -d headsup < scripts/part2b/load-trade-history.sql   # 2,000,000 trades, ~4,000 per stock
docker compose exec -T postgres psql -U headsup -d headsup < scripts/part2b/load-hot-stock.sql       # +500,000 trades in AAPL
```

Both loads are safe to rerun. Undo the second with `DELETE FROM trades WHERE account_id = 'usr_archive_hot';`.

Every request the traffic script sends carries `User-Agent: part2b-<label>`, so a run is found in Jaeger (http://localhost:16686, service `trading-api`) with the tag `http.user_agent=part2b-<label>`. Filter on the outer `GET …` / `POST …` operation; the tag is on that span.

Durations below were measured on one laptop and will differ elsewhere. The ratios are the point.

If requests start failing with `timeout exceeded when trying to connect`, run `docker compose restart trading-api`. The service's transaction helper (`src/db/pool.js`, unchanged from `main`) does not release its connection when it retries a cancelled statement, so a burst of cancelled fills can use up the pool.

## Part 2b: three slow queries

### 1. Missing index: always slow

```bash
bash scripts/part2b/traffic.sh trades 50 trades-before
docker compose exec -T postgres psql -U headsup -d headsup < scripts/part2b/index-drop.sql
bash scripts/part2b/traffic.sh trades 50 trades-after
docker compose exec -T postgres psql -U headsup -d headsup < scripts/part2b/index-create.sql        # restore
```

Jaeger operation `GET /stocks/:symbol/trades`. The recent-trades query span goes from about 0.9 ms to about 72 ms. Its text and its eleven tags are identical in both runs. No code change, no restart.

### 2. Data skew: slow for one input

```bash
bash scripts/part2b/traffic.sh summary 50 summary
```

Jaeger operation `GET /stocks/:symbol/trades/summary`. Ten stocks in rotation: nine take about 10 ms, AAPL about 75 ms. Same SQL, same index, same tags. The stock appears only on the request span (`app.symbol`), not on the query span.

### 3. Lock contention: slow only when requests overlap

```bash
docker compose stop load-generator      # see below
sleep 60
bash scripts/part2b/traffic.sh mixed orders-mixed
docker compose start load-generator
```

The script places its orders on the same ten accounts the load generator uses, and `fraud-service` refuses an account that places more than 10 orders in a minute (`TRADE_VELOCITY`, status 422). With the load generator running, some of the script's orders are refused before they reach the lock. Stopping it and waiting out the one-minute window gives a run where all 47 orders are filled.

Jaeger operation `POST /`. 35 orders one at a time, and two bursts of six at the same moment on one account. The statement `SELECT id, cash FROM accounts WHERE id = $1 FOR UPDATE` takes 0.6 to 2.4 ms alone and 10 to 132 ms inside a burst. The service code is as shipped.

### Tools

```bash
node scripts/part2b/capture.mjs "<jaeger url>" out.png --clip .SearchResults--header      # screenshot; Node 22+, Microsoft Edge
python scripts/part2b/mock/build.py query-monitoring-mock.html                             # per-query page built from recorded runs
```

The mock page reads three runs by label: `trades-cycle` (the `trades` traffic sent with one label, half before `index-drop.sql` and half after), `summary`, and `orders-mixed2`. To feed it, send the lock traffic with that label: `bash scripts/part2b/traffic.sh mixed orders-mixed2`.

## Part 3: event-loop busy time on client spans

The proposal: for every span of kind "client", record how long the event loop was busy while the span was open, so a slow query span can be told apart from a slow app.

```bash
mkdir /tmp/otel && (cd /tmp/otel && npm init -y && npm install @opentelemetry/api @opentelemetry/sdk-trace-base)
node scripts/part3/processor-test.js /tmp/otel
```

Expected: the tag `nodejs.eventloop.busy_ms` is 0 on a normal client span, about 290 and 150 on the two spans whose thread was blocked, and absent on the span that is not of kind "client". One span processor, no plug-in changed. The outside system is a stand-in (a 10 ms timer), not this app's database.

```bash
pip install pillow
python scripts/part3/make-gif.py event-loop.gif        # the animation; uses Windows fonts
```
