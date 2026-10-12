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

/**
 * Six months of activity in one stock: how many trades, how much volume, and the range
 * of prices paid.
 *
 * Unlike the list above, this cannot stop at fifty rows. An aggregate has to read every
 * trade it summarises, so its cost follows how actively the stock trades — and stocks
 * are not traded equally.
 */
async function getTradeSummary(symbol) {
  const { rows } = await query(
    `SELECT count(*)::int          AS trades,
            COALESCE(sum(quantity), 0)::bigint AS volume,
            avg(price)             AS average_price,
            min(price)             AS low,
            max(price)             AS high
     FROM trades
     WHERE symbol = $1
       AND executed_at >= now() - interval '180 days'`,
    [String(symbol).toUpperCase()],
  );

  const row = rows[0];
  return {
    trades: row.trades,
    volume: row.volume,
    averagePrice: row.average_price === null ? null : Math.round(row.average_price * 10000) / 10000,
    low: row.low,
    high: row.high,
    periodDays: 180,
  };
}

module.exports = { getRecentTrades, getTradeSummary };
