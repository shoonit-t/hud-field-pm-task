-- Part 2b: give `trades` a production-sized history.
--
-- The seeded database holds a few hundred trades, and at that size no query on the table
-- can be slow whatever it does. This adds 2,000,000 executions spread evenly over every
-- stock and the last 180 days, owned by 20 archive accounts.
--
-- The archive accounts are new, so nothing changes for the accounts the app and the load
-- generator use: their reads all filter by account.
--
-- Safe to run twice: it does nothing if the archive accounts already exist.
-- Undo with `make reset`, which rebuilds the database.
--
--   docker compose exec -T postgres psql -U headsup -d headsup < scripts/part2b/load-trade-history.sql

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM accounts WHERE id = 'usr_archive_01') THEN
    RAISE NOTICE 'trade history already loaded - nothing to do';
    RETURN;
  END IF;

  INSERT INTO accounts (id, username, username_key, display_name, email, account_number,
                        account_type, risk_profile, advisor, member_since)
  SELECT 'usr_archive_' || lpad(n::text, 2, '0'),
         'archive-' || lpad(n::text, 2, '0'),
         'archive-' || lpad(n::text, 2, '0'),
         'Archive account ' || n,
         'archive-' || lpad(n::text, 2, '0') || '@example.invalid',
         'ARC-' || lpad(n::text, 6, '0'),
         'Individual', 'Balanced', 'None', CURRENT_DATE - 365
  FROM generate_series(1, 20) AS n;

  -- Each generated row draws a stock, a side, a size, a price near that stock's base
  -- price, and a moment in the last 180 days. Materialized so every random() is drawn
  -- once per row rather than re-evaluated by the join.
  INSERT INTO trades (account_id, symbol, side, quantity, price, cash_delta, realized_pnl,
                      trade_date, executed_at)
  WITH numbered AS MATERIALIZED (
    SELECT symbol, base_price, row_number() OVER (ORDER BY symbol) AS rn FROM stocks
  ),
  draws AS MATERIALIZED (
    SELECT i,
           1 + floor(random() * (SELECT count(*) FROM stocks))::int AS rn,
           random() < 0.5                                           AS is_buy,
           1 + floor(random() * 200)::bigint                        AS quantity,
           0.8 + random() * 0.4                                     AS price_factor,
           now() - random() * interval '180 days'                   AS executed_at
    FROM generate_series(1, 2000000) AS i
  ),
  priced AS (
    SELECT d.i, s.symbol, d.is_buy, d.quantity, d.executed_at,
           round((s.base_price * d.price_factor)::numeric, 4) AS price
    FROM draws d JOIN numbered s USING (rn)
  )
  SELECT 'usr_archive_' || lpad((1 + i % 20)::text, 2, '0'),
         symbol,
         CASE WHEN is_buy THEN 'BUY' ELSE 'SELL' END,
         quantity,
         price,
         round(quantity * price, 2) * CASE WHEN is_buy THEN -1 ELSE 1 END,
         NULL,
         executed_at::date,
         executed_at
  FROM priced;
END $$;

-- Refresh the planner's statistics so it knows how large the table now is.
ANALYZE trades;

SELECT count(*) AS trades_total FROM trades;
