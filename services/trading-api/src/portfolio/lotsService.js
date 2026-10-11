/**
 * Holdings broken down by purchase lot — the tax-lot view.
 *
 * `GET /api/portfolio` reports one line per stock. This is the level beneath it: each
 * separate purchase still held, what it cost, and what it is worth now. It is what an
 * investor reads to decide *which* shares to sell, since lots bought at different times
 * and prices are taxed differently.
 *
 * One query. The data is nested — positions, lots within them, a price for each — and it
 * is still a single join.
 */
const { query } = require('../db/pool.js');

const round2 = (value) => Math.round(value * 100) / 100;
const pct = (part, whole) => (whole > 0 ? round2((part / whole) * 100) : 0);

const MS_PER_DAY = 86_400_000;
// The holding period after which a gain is treated as long-term.
const LONG_TERM_DAYS = 365;

/** Whole days between a `YYYY-MM-DD` purchase date and now. */
const daysHeld = (openedOn, now) =>
  Math.max(0, Math.floor((now - Date.parse(`${openedOn}T00:00:00Z`)) / MS_PER_DAY));

/** One lot, valued at the current price. */
function describeLot(row, now) {
  const costBasis = round2(row.quantity * row.cost_price);
  const marketValue = round2(row.quantity * row.price);
  const unrealizedPnl = round2(marketValue - costBasis);
  const held = daysHeld(row.opened_on, now);

  return {
    lotId: row.lot_id,
    openedOn: row.opened_on,
    daysHeld: held,
    longTerm: held > LONG_TERM_DAYS,
    quantity: row.quantity,
    costPrice: row.cost_price,
    costBasis,
    marketValue,
    unrealizedPnl,
    unrealizedPnlPercent: pct(unrealizedPnl, costBasis),
  };
}

async function getLots(user) {
  const { rows } = await query(
    `SELECT p.symbol, i.name, q.price,
            l.id                                       AS lot_id,
            l.trade_date                               AS opened_on,
            (l.quantity - l.closed_quantity)::bigint   AS quantity,
            l.price                                    AS cost_price
     FROM positions p
     JOIN stocks i ON i.symbol = p.symbol
     JOIN quotes q ON q.symbol = p.symbol
     JOIN lots l   ON l.position_id = p.id
     WHERE p.account_id = $1
       -- A fully sold lot stays as history but is not a holding.
       AND l.quantity > l.closed_quantity
     ORDER BY p.symbol, l.trade_date, l.id`,
    [user.id],
  );

  const now = Date.now();
  const positions = [];
  let current = null;

  for (const row of rows) {
    if (current?.symbol !== row.symbol) {
      current = { symbol: row.symbol, name: row.name, price: row.price, quantity: 0, lots: [] };
      positions.push(current);
    }
    current.quantity += row.quantity;
    current.lots.push(describeLot(row, now));
  }

  return {
    positions,
    positionCount: positions.length,
    lotCount: rows.length,
    asOf: new Date(now).toISOString(),
  };
}

module.exports = { getLots };
