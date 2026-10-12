-- Part 2b: make one stock far more actively traded than the rest.
--
-- load-trade-history.sql spreads its trades evenly, about 4,000 per stock. Real markets
-- are not even: a handful of names account for a large share of all trading. This adds
-- 500,000 trades in AAPL over the same 180 days, so a query that reads "all trades in a
-- stock" has 4,000 rows to read for most stocks and about 504,000 for this one.
--
-- The rows belong to one account of their own, so they can be removed without touching
-- anything else:
--
--   DELETE FROM trades WHERE account_id = 'usr_archive_hot';
--
-- Safe to run twice: it does nothing if that account already exists.
--
--   docker compose exec -T postgres psql -U headsup -d headsup < scripts/part2b/load-hot-stock.sql

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM accounts WHERE id = 'usr_archive_hot') THEN
    RAISE NOTICE 'hot stock already loaded - nothing to do';
    RETURN;
  END IF;

  INSERT INTO accounts (id, username, username_key, display_name, email, account_number,
                        account_type, risk_profile, advisor, member_since)
  VALUES ('usr_archive_hot', 'archive-hot', 'archive-hot', 'Archive account (AAPL)',
          'archive-hot@example.invalid', 'ARC-HOT001', 'Individual', 'Balanced', 'None',
          CURRENT_DATE - 365);

  INSERT INTO trades (account_id, symbol, side, quantity, price, cash_delta, realized_pnl,
                      trade_date, executed_at)
  WITH draws AS MATERIALIZED (
    SELECT random() < 0.5                         AS is_buy,
           1 + floor(random() * 200)::bigint      AS quantity,
           0.8 + random() * 0.4                   AS price_factor,
           now() - random() * interval '180 days' AS executed_at
    FROM generate_series(1, 500000)
  ),
  priced AS (
    SELECT d.is_buy, d.quantity, d.executed_at,
           round((s.base_price * d.price_factor)::numeric, 4) AS price
    FROM draws d CROSS JOIN (SELECT base_price FROM stocks WHERE symbol = 'AAPL') s
  )
  SELECT 'usr_archive_hot',
         'AAPL',
         CASE WHEN is_buy THEN 'BUY' ELSE 'SELL' END,
         quantity,
         price,
         round(quantity * price, 2) * CASE WHEN is_buy THEN -1 ELSE 1 END,
         NULL,
         executed_at::date,
         executed_at
  FROM priced;
END $$;

-- Refresh the planner's statistics so it knows how uneven the table now is.
ANALYZE trades;

SELECT count(*) AS trades_total,
       count(*) FILTER (WHERE symbol = 'AAPL') AS aapl
FROM trades;
