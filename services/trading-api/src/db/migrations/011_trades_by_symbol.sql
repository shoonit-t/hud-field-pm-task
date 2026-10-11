-- Recent trades for one stock, newest first.
--
-- Every read of `trades` so far has been "what did this account do", which is what
-- `trades_account_date_idx` serves. `GET /api/market/stocks/:symbol/trades` is the first
-- to ask "what traded in this stock, by anyone", and without an index of its own that
-- question is a scan of the whole table.
--
-- `executed_at DESC` is in the index so the newest fifty come straight off it in order,
-- with no sort step.
CREATE INDEX trades_symbol_executed_idx ON trades (symbol, executed_at DESC);
