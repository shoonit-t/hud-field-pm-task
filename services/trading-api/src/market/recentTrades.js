/**
 * The most recent executions in one stock — the "time and sales" list on a stock page.
 *
 * Reads `trades` across every account, which nothing else does: the portfolio reads are
 * all scoped to one account. It is served by `trades_symbol_executed_idx` (migration 011).
 *
 * No account is returned. Who traded is private; what traded, when, and at what price is
 * what the tape shows.
 */
const { query } = require('../db/pool.js');

async function getRecentTrades(symbol, { limit = 50 } = {}) {
  const { rows } = await query(
    `SELECT side, quantity, price, executed_at
     FROM trades
     WHERE symbol = $1
     ORDER BY executed_at DESC
     LIMIT $2`,
    [String(symbol).toUpperCase(), limit],
  );

  return rows.map((row) => ({
    side: row.side,
    quantity: row.quantity,
    price: row.price,
    executedAt: row.executed_at,
  }));
}

module.exports = { getRecentTrades };
