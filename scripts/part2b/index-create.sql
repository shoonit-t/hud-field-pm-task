-- Part 2b, missing index: the "before" state. Same definition as migration 011.
CREATE INDEX IF NOT EXISTS trades_symbol_executed_idx ON trades (symbol, executed_at DESC);
