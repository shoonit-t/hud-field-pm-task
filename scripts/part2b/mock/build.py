"""Part 2b: build the query-monitoring mock page from this project's real traces.

    python scripts/part2b/mock/build.py notes/reference/query-monitoring-mock.html

Reads the three labelled runs out of Jaeger, groups the query spans by SQL text, and
writes one self-contained HTML page. Durations, counts and trace links are measured.
Plans and row counts are what Postgres reported when EXPLAIN ANALYZE was run by hand.
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

JAEGER = "http://localhost:16686"
BURST_USERS = {"l.zhang", "m.rossi"}


def traces(operation, label):
    query = urllib.parse.urlencode(
        {
            "service": "trading-api",
            "operation": operation,
            "limit": 300,
            "lookback": "24h",
            "tags": json.dumps({"http.user_agent": label}),
        }
    )
    return json.load(urllib.request.urlopen(f"{JAEGER}/api/traces?{query}"))["data"]


def runs(operation, label, needle, group_of, param_tag):
    out = []
    for trace in traces(operation, label):
        root = next(s for s in trace["spans"] if not s["references"])
        tags = {t["key"]: t["value"] for t in root["tags"]}
        for span in trace["spans"]:
            statement = "".join(str(t["value"]) for t in span["tags"] if t["key"] == "db.statement")
            if needle in statement:
                out.append(
                    {
                        "start": span["startTime"],
                        "d": round(span["duration"] / 1000, 3),
                        "p": tags.get(param_tag),
                        "t": trace["traceID"],
                        "tags": tags,
                    }
                )
    out.sort(key=lambda r: r["start"])
    for index, run in enumerate(out):
        run["g"] = group_of(run, index, len(out))
        del run["start"], run["tags"]
    return out


queries = [
    {
        "title": "Recent trades for a stock",
        "short": "SELECT side, quantity, price, executed_at FROM trades WHERE symbol = $1 ORDER BY executed_at DESC LIMIT $2",
        "sql": "SELECT side, quantity, price, executed_at\nFROM trades\nWHERE symbol = $1\nORDER BY executed_at DESC\nLIMIT $2",
        "insight": "Index recommendation: trades (symbol, executed_at)",
        "rowsRead": "50, then 2,000,000",
        "groups": ["Index present", "Index removed"],
        "chartNote": "Case 1, missing index. The index was dropped halfway through; every execution after that is slow.",
        "runs": runs(
            "GET /stocks/:symbol/trades",
            "part2b-trades-cycle",
            "ORDER BY executed_at",
            lambda run, index, total: 0 if index < total // 2 else 1,
            "app.symbol",
        ),
        "paramLabel": "Stock (from the app's own tag)",
        "paramNote": "The parameter does not explain it: every stock is slow once the index is gone.",
        "plans": [
            {
                "name": "Index Scan",
                "when": "while the index existed",
                "text": "Limit (rows=50)\n  ->  Index Scan using trades_symbol_executed_idx on trades (rows=50)\n        Index Cond: (symbol = 'NXPI')\nExecution Time: 0.471 ms",
            },
            {
                "name": "Parallel Seq Scan",
                "when": "after the index was dropped",
                "text": "Limit (rows=50)\n  ->  Gather Merge (workers: 2)\n        ->  Sort (Sort Key: executed_at DESC)\n              ->  Parallel Seq Scan on trades (rows=1344 per worker)\n                    Filter: (symbol = 'NXPI')\n                    Rows Removed by Filter: 665667 per worker\nExecution Time: 76.221 ms",
            },
        ],
        "blocking": None,
        "endpoint": "GET /api/market/stocks/:symbol/trades",
        "position": "Third and last query of the request",
    },
    {
        "title": "Six-month trading summary for a stock",
        "short": "SELECT count(*), sum(quantity), avg(price), min(price), max(price) FROM trades WHERE symbol = $1 AND executed_at >= now() - interval '180 days'",
        "sql": "SELECT count(*), sum(quantity), avg(price), min(price), max(price)\nFROM trades\nWHERE symbol = $1\n  AND executed_at >= now() - interval '180 days'",
        "insight": None,
        "rowsRead": "3,900 or 504,000",
        "groups": ["Nine typical stocks", "AAPL"],
        "chartNote": "Case 2, data skew. Same SQL, same index. One execution in ten is slow, and it is always the same stock.",
        "runs": runs(
            "GET /stocks/:symbol/trades/summary",
            "part2b-summary",
            "count(*)",
            lambda run, index, total: 1 if run["p"] == "AAPL" else 0,
            "app.symbol",
        ),
        "paramLabel": "Stock (from the app's own tag)",
        "paramNote": "The query span records only $1. The stock is known here because this app's developers tagged it on the request.",
        "plans": [
            {
                "name": "Bitmap Heap Scan",
                "when": "typical stock (KO)",
                "text": "Aggregate\n  ->  Bitmap Heap Scan on trades (rows=3913)\n        ->  Bitmap Index Scan on trades_symbol_executed_idx (rows=3913)\nExecution Time: 18.4 ms (first run)",
            },
            {
                "name": "Parallel Bitmap Heap Scan",
                "when": "AAPL",
                "text": "Finalize Aggregate\n  ->  Gather (workers: 2)\n        ->  Partial Aggregate\n              ->  Parallel Bitmap Heap Scan on trades (rows=167991 per worker)\n                    ->  Bitmap Index Scan on trades_symbol_executed_idx (rows=503973)\nExecution Time: 110.8 ms (first run)",
            },
        ],
        "blocking": None,
        "endpoint": "GET /api/market/stocks/:symbol/trades/summary",
        "position": "Third and last query of the request",
    },
    {
        "title": "Lock the account row (placing an order)",
        "short": "SELECT id, cash FROM accounts WHERE id = $1 FOR UPDATE",
        "sql": "SELECT id, cash FROM accounts WHERE id = $1 FOR UPDATE",
        "insight": None,
        "rowsRead": "1",
        "groups": ["Order arrived alone", "Six orders at once on one account"],
        "chartNote": "Case 3, lock contention. Unmodified code. The statement is slow only when orders for one account overlap.",
        "runs": runs(
            "POST /",
            "part2b-orders-mixed2",
            "FOR UPDATE",
            lambda run, index, total: 1 if run["p"] in BURST_USERS else 0,
            "app.username",
        ),
        "paramLabel": "User (from the app's own tag)",
        "paramNote": "Not tied to an input: the same accounts are fast at other moments.",
        "plans": [
            {
                "name": "Index Scan",
                "when": "fast and slow executions alike",
                "text": "LockRows\n  ->  Index Scan using accounts_pkey on accounts (rows=1)\n        Index Cond: (id = $1)\n\nThe plan is the same whether the statement takes 1 ms or 130 ms.\n(Plan shape shown from the query's structure; not captured during the run.)",
            }
        ],
        "blocking": {
            "note": "One burst of six orders for user l.zhang. Durations are measured. The last two columns are illustrative: they show what a database-side tool would add, and nothing in our traces records them.",
            "rows": [
                ["1st", "10.1 ms", "nothing", "nobody"],
                ["2nd", "21.0 ms", "row lock on accounts", "the 1st order"],
                ["3rd", "39.7 ms", "row lock on accounts", "the 2nd order"],
                ["4th", "63.3 ms", "row lock on accounts", "the 3rd order"],
                ["5th", "104.0 ms", "row lock on accounts", "the 4th order"],
                ["6th", "132.1 ms", "row lock on accounts", "the 5th order"],
            ],
        },
        "endpoint": "POST /api/orders",
        "position": "Inside the order's transaction, right after BEGIN",
    },
    {
        "title": "Login check (healthy, for comparison)",
        "short": "SELECT * FROM accounts WHERE id = $1",
        "sql": "SELECT * FROM accounts WHERE id = $1",
        "insight": None,
        "rowsRead": "1",
        "groups": ["All executions"],
        "chartNote": "A healthy query: every authenticated request runs it, and it is always fast.",
        "runs": runs(
            "GET /stocks/:symbol/trades/summary",
            "part2b-summary",
            "SELECT * FROM accounts WHERE id",
            lambda run, index, total: 0,
            "app.username",
        ),
        "paramLabel": "User (from the app's own tag)",
        "paramNote": "",
        "plans": [
            {
                "name": "Index Scan",
                "when": "every execution",
                "text": "Index Scan using accounts_pkey on accounts (rows=1)\n\n(Plan shape shown from the query's structure; not captured during the run.)",
            }
        ],
        "blocking": None,
        "endpoint": "every authenticated endpoint",
        "position": "First query of the request",
    },
]

for query in queries:
    if not query["runs"]:
        sys.exit(f"no traces found for: {query['title']} (has Jaeger been restarted?)")
    print(f"{query['title']}: {len(query['runs'])} executions")

template = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
out = Path(sys.argv[1])
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(template.replace("__DATA__", json.dumps({"queries": queries})), encoding="utf-8", newline="\n")
print(f"wrote {out}")
