-- Part 2b, missing index: the "after" state. Recent-trades now scans the whole table.
-- Restore with index-create.sql.
-- CONCURRENTLY, so orders being placed are not blocked while the index is removed.
DROP INDEX CONCURRENTLY IF EXISTS trades_symbol_executed_idx;
