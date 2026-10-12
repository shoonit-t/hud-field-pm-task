-- Part 2b, missing index: the "before" state. Same definition as migration 011.
-- CONCURRENTLY, so orders being placed are not blocked while the index is built.
CREATE INDEX CONCURRENTLY IF NOT EXISTS trades_symbol_executed_idx ON trades (symbol, executed_at DESC);
