-- Part 2b, missing index: the "after" state. Recent-trades now scans the whole table.
-- Restore with index-create.sql.
DROP INDEX IF EXISTS trades_symbol_executed_idx;
