# Paper order contract and provenance

The order endpoints of the main API (`api/main.py`) expose the ledger of the
paper executor: what was requested, what actually filled, what is still open,
and what it cost. Every row is self-describing, so a consumer never has to
guess which execution venue produced it.

## Provenance

`GET /orders` and `POST /orders` are served by the paper executor only — there
is no live exchange order path behind them. Each row therefore carries
`"mode": "paper"`. The marker exists so a future live-order surface can be
added without consumers silently mis-reading paper fills as real ones, and the
dashboard renders it as a `PAPER` badge next to every order.

`mode` is a contract field, not a label: treat any other value as an order that
did not come from this endpoint.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /orders` | List orders. Optional `symbol` and `status` query filters. |
| `GET /orders/{order_id}` | Single order, same row shape as the list. `404` for an unknown id. |
| `POST /orders` | Place an order; the response carries the same row under `order`. |
| `DELETE /orders/{order_id}` | Cancel a `PENDING` order; the cancelled row stays in the ledger. |

`status` accepts every executor state: `PENDING`, `FILLED`, `CANCELLED`,
`PARTIAL`, `MISSED`. Any other value is a `422` validation error rather than a
silently empty list.

The single-order route is registered after the static `/orders` route and is
the only parametrized `GET` under `/orders`, so it cannot shadow another path.
A non-numeric id is a `422`; an unknown numeric id is a structured `404`:

```json
{"detail": {"error": "not_found", "message": "Order 999 not found"}}
```

## Row fields

All amounts are string-encoded decimals; the wire format never rounds a
quantity, a price or a fee.

| Field | Meaning |
|---|---|
| `order_id` | Executor order id (integer, monotonic per process). |
| `mode` | Provenance; `paper` for everything this API serves. |
| `symbol`, `side`, `order_type` | Order identity: `BTCUSD`, `BUY`/`SELL`, `market`/`limit`. |
| `status` | `PENDING`, `FILLED`, `CANCELLED`, `PARTIAL` or `MISSED`. |
| `requested_qty` | Quantity the order asked for. |
| `filled_qty` | Quantity that actually traded. `0` for `PENDING`, `MISSED` and `CANCELLED`. |
| `remaining_qty` | `requested_qty - filled_qty`. |
| `fill_ratio` | `filled_qty / requested_qty`, quantized to 4 decimals; `0` when nothing traded. |
| `avg_fill_price` | Price the filled quantity traded at (slippage applied); `null` when nothing filled. |
| `limit_price` | Limit price of a limit order; `null` for market orders. |
| `fees` | Fees charged on the filled notional. |
| `slippage_bps` | Slippage applied to the order, in basis points. |
| `created_at`, `filled_at` | Lifecycle timestamps (`filled_at` is `null` until a fill). |

### Why some values are normalized

Two normalizations live in the API mapping (`_paper_order_fill_progress` /
`_order_to_response`), not in the executor:

- **A resting limit order carries `fill_qty == qty` in the executor** until its
  price crosses. Reporting that field verbatim would claim a `PENDING` order was
  fully filled, so `filled_qty` is only taken from the executor once the order
  reached `FILLED` or `PARTIAL`.
- **The market executor derives `fill_price` before simulating the fill**, so a
  `MISSED` order would advertise a price for a fill that never happened. Any row
  with `filled_qty == 0` therefore reports `avg_fill_price: null`.

`fill_ratio` is derived from the same normalized `filled_qty`, so
`filled_qty`, `remaining_qty` and `fill_ratio` always agree within one row.

## Partial and missed fills

`PARTIAL` and `MISSED` are first-class states, not error codes:

- `PARTIAL` — a market order filled less than requested (the executor simulates
  a fill ratio between its `min_fill_ratio` and 1); `remaining_qty` is what did
  not trade.
- `MISSED` — the order did not trade at all; positions are unchanged.

Both keep their row in the ledger and can be requested through the `status`
filter, so a consumer can audit missed execution instead of only seeing the
orders that worked.

## Dashboard wiring

`frontend/src/api/trading.ts` calls `${API_BASE}/orders` with the optional
`symbol`/`status` query parameters, and `frontend/src/components/OrdersTable.tsx`
renders the full contract: requested/filled/remaining quantity with fill
percentage, average fill price, fees, slippage, the provenance badge and a
status colour per state (`PARTIAL` and `MISSED` are styled distinctly from
`CANCELLED`). `App.tsx` polls the endpoints every 5 seconds.

## Out of scope

- Order-status push over WebSocket (the WS lane is prices-only).
- Enabling durable `paper_orders` persistence on the API executor path; the
  ledger documented here is in-process state.
