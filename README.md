# AI Investment Intelligence — POC (Indian equities, paper trading)

A small, runnable proof of concept: a portfolio tracker for Indian stocks with a stock explorer,
technical indicators, **paper (simulated) trading**, and plain-English AI insights.

> **Simulation only.** Virtual money (₹1,00,000 starting cash). No broker connection, no live orders,
> no real payments. The bundled market data is **simulated** (a seeded random walk), not real prices.
> Nothing in the app is investment advice.

| Area | Status |
|---|---|
| Portfolio dashboard (value, cash, invested, realized/unrealized P&L, return, holdings, performance chart) | ✅ |
| Stock explorer (latest/previous close, % change, history chart, SMA 20/50, RSI 14, volatility, data label + timestamp) | ✅ |
| Paper trading (buy/sell, confirmation step, validation, charges estimate, idempotency, order + trade log) | ✅ |
| AI insights (deterministic rules; optional Claude summary of the same metrics) | ✅ |
| Market-data provider interface + CSV/simulated provider | ✅ |
| Upstox adapter | Placeholder only (see [Market data](#market-data)) |
| Razorpay test payments | Deferred (out of scope for this milestone) |

---

## Quick start (Docker, recommended)

Requirements: **Docker Desktop** (running), ~4 GB free RAM, ports `3000`, `8000`, `5433` free.

```bash
cp .env.example .env        # optional; every value has a working default
docker compose up --build
```

- App: <http://localhost:3000>
- API docs (Swagger): <http://localhost:8000/docs>

On start the backend runs migrations, loads the market data, and creates a demo account with a few
seeded trades (idempotent — restarting keeps your trades).

If a port is taken, change `FRONTEND_PORT`, `BACKEND_PORT` or `DB_PORT` in `.env`.
The database is published on host port **5433** (not 5432) to avoid clashing with a local PostgreSQL.

Useful commands:

```bash
docker compose exec backend pytest                         # run the test suite (uses a separate finance_test DB)
docker compose exec backend python -m scripts.seed --reset # wipe the paper account and re-seed demo trades
docker compose exec backend python -m scripts.seed --reset --empty  # fresh ₹1,00,000 account, no trades
docker compose down          # stop (data kept in the pgdata volume)
docker compose down -v       # stop and delete all data
```

## Running without Docker (development)

You still need PostgreSQL; the simplest is `docker compose up -d db`.

```bash
# Backend (Python 3.12+)
cd backend
python -m venv .venv
.venv/Scripts/activate            # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload     # http://localhost:8000
pytest                            # unit tests run without a DB; integration tests need finance_test

# Frontend (Node 20.9+)
cd frontend
npm install
npm run dev                       # http://localhost:3000, proxies /api to http://localhost:8000
```

The backend reads `.env` from the repo root. Outside Docker, `DATABASE_URL` / `TEST_DATABASE_URL`
from `.env.example` point at `localhost:5433`.

---

## Architecture

```
frontend (Next.js 16, TS, Tailwind 4, Recharts)  ──/api/* proxy──▶  backend (FastAPI)  ──▶  PostgreSQL 16
                                                                       │
                                            market-data provider ──────┘ (sync into DB)
                                            optional Anthropic API (insight summary)
```

- The browser only talks to the Next.js server; `/api/*` is proxied to FastAPI, so no API URL
  or secret reaches the client.
- **Market data flows provider → database → API.** A provider (CSV today) is synced into the
  `price_bars` table by the seed script; endpoints read from the DB. Swapping providers means changing
  `MARKET_DATA_PROVIDER` and re-running the sync — no endpoint changes.
- **Financial math is pure and separate** (`backend/app/services/portfolio.py`, `indicators.py`):
  no DB access, deterministic, fully unit-tested.

```
backend/
  app/config.py              settings from env (.env)
  app/models.py              SQLAlchemy models
  app/schemas.py             request/response schemas (Swagger)
  app/market/                provider interface, CSV provider, Upstox placeholder, DB sync
  app/services/portfolio.py  P&L, average cost, fees, order validation, ledger replay (pure)
  app/services/indicators.py SMA, RSI (Wilder), historical volatility (pure)
  app/services/trading.py    order execution in one DB transaction (row lock + idempotency)
  app/services/insights.py   rule-based insights + optional Claude summary
  app/routers/               HTTP endpoints
  alembic/                   migrations
  scripts/seed.py            load data + demo account (idempotent; --reset)
  scripts/generate_fixtures.py  regenerate the simulated CSV fixtures
  data/fixtures/             simulated EOD CSVs (5 NSE symbols, 260 trading days to 23 Oct 2026)
  tests/                     pytest: unit + DB + API integration
frontend/
  app/                       dashboard, /stocks, /stocks/[symbol], /transactions
  components/                charts, trade dialog, holdings table, insights panel, UI states
  lib/api.ts                 typed API client
```

### Accounting model

- A holding stores `quantity` and `cost_basis` (₹ paid for the shares still held, **including the
  estimated buy charges**). Average cost = cost basis ÷ quantity.
- A sell removes a proportional slice of cost basis; **realized P&L = net proceeds (after estimated
  sell charges) − that slice**. Selling the whole position removes the exact remaining cost basis.
- All money is `NUMERIC(14,2)` / Python `Decimal`, rounded half-up to the paisa. With this model
  `total P&L = realized + unrealized = portfolio value − initial cash` holds exactly (tested).
- Orders execute at the **latest available close** for the symbol (EOD data), labelled as such.
- Charges are a configurable **estimate** — `PAPER_FEE_PERCENT` % of order value + `PAPER_FEE_FLAT` ₹
  (default 0.10% + ₹0). They do not model real brokerage, STT, GST, stamp duty or exchange fees.

### Reliability

- Each order runs in one transaction that locks the account row (`SELECT … FOR UPDATE`), so cash
  and holdings can't diverge under concurrent requests. DB check constraints back this up
  (`cash >= 0`, `quantity > 0`).
- **Duplicate protection:** the UI sends an `Idempotency-Key` header per confirmed order; the key is
  unique in the DB, and a resend returns the original order (`"replayed": true`) without trading twice.
- Rejected orders (insufficient cash/holdings) are recorded with a reason; invalid input
  (quantity ≤ 0, fractional, unknown side, malformed symbol) is rejected with `422` and not recorded.

---

## API

Full interactive docs at `/docs`. All endpoints are JSON.

| Method & path | Purpose |
|---|---|
| `GET /api/health` | DB status, configured provider, whether the LLM is enabled |
| `GET /api/stocks?q=` | Instruments with latest/previous close, change, data status, timestamp |
| `GET /api/stocks/{symbol}/quote` | Latest quote + SMA 20/50, RSI 14, 20-day volatility |
| `GET /api/stocks/{symbol}/history?days=180` | Daily OHLCV with SMA/RSI per day |
| `GET /api/portfolio` | Summary + holdings |
| `GET /api/portfolio/history` | Daily portfolio value rebuilt from the trade ledger |
| `GET /api/portfolio/transactions` | Executed paper trades |
| `POST /api/paper-trades/preview` | Price an order (same math as execution), no side effects |
| `POST /api/paper-trades` | Execute a paper order. Header `Idempotency-Key` (8–64 chars) recommended |
| `GET /api/paper-trades` | All paper orders including rejected ones |
| `GET /api/insights` | Rule-based insights (+ optional Claude summary), disclaimer, metrics used |

Errors use `{"detail": {"code": "INSUFFICIENT_CASH", "message": "…", "order_id": 12}}`
(`400` rejected, `404` unknown symbol, `503` no price, `422` validation).

**Changes from the original spec:** `POST /api/portfolio/holdings` was dropped — holdings change only
through paper trades (“add” = buy, “remove” = sell all) so cash and P&L always reconcile.
`/api/paper-trades/preview`, `GET /api/paper-trades` and `/api/portfolio/history` were added.
The `/api/payments/*` endpoints are not implemented (Razorpay deferred).

---

## Market data

**Default: simulated.** `backend/data/fixtures/*.csv` hold 260 weekdays (to 23 Oct 2026) of
generated OHLCV for RELIANCE, TCS, INFY, HDFCBANK and ICICIBANK. They are produced by
`python -m scripts.generate_fixtures` (seeded geometric Brownian motion). **They are not real prices**;
the UI labels them “Simulated data” with the as-of timestamp everywhere prices appear.

**Using real end-of-day data you are licensed to use:** put `instruments.csv`
(`symbol,name,exchange,sector`) and one `<SYMBOL>.csv` (`date,open,high,low,close,volume`) per symbol
in a folder, set `MARKET_DATA_DIR` to it and `CSV_DATA_STATUS=HISTORICAL`, then run
`python -m scripts.seed`. Check the source's licence/terms first; this project does not scrape
websites or call unofficial endpoints.

**Provider interface** (`app/market/base.py`): `list_instruments(query)`, `get_quote(symbol)`,
`get_history(symbol, start, end)`, plus `source` and `status` (`LIVE | DELAYED | HISTORICAL | SIMULATED`).

### Upstox (not implemented — what you need)

`MARKET_DATA_PROVIDER=upstox` selects a placeholder that raises a clear error. To implement it:

1. Open an Upstox account and create an app in the Upstox developer console
   (<https://upstox.com/developer/>) to get an **API key, API secret and redirect URL**.
2. Implement the OAuth login flow to obtain an **access token**. Upstox community moderators state
   tokens must be regenerated **daily**, so a scheduled re-auth step is needed.
3. Use the documented historical-candle endpoints (v2 `/historical-candle/…`, and v3 variants for
   historical vs. intraday data) with instrument keys from Upstox's published instrument files.
4. **Review Upstox's API terms and rate limits** before storing or displaying the data.

Notes from research (Oct 2026): Upstox's SDK documents a sandbox flag that is aimed at **order
placement**; I found no confirmation that the sandbox serves historical market data, so don't assume
it does. The app stays fully runnable without any Upstox credentials.
Sources: [Upstox Python SDK on PyPI](https://pypi.org/project/upstox-python-sdk/),
[Upstox community: production access](https://community.upstox.com/t/request-for-production-access-for-my-upstox-app/11273),
[Upstox community: API Q&A](https://community.upstox.com/t/regarding-upstox-api/11249).

---

## AI insights

`GET /api/insights` always returns **deterministic rule-based** explanations computed from backend
metrics: overall performance, sector concentration (≥ 40% of holdings), single-stock weight
(≥ 30%), cash share, RSI ≥ 70 / ≤ 30, price vs. 50-day SMA (≥ 5% gap), and high volatility (≥ 35%).

If `ANTHROPIC_API_KEY` is set, Claude additionally writes a ≤ 120-word plain-English summary. It
receives **only the computed metrics JSON and the rule outputs**, and is instructed not to add prices,
news, events, forecasts or buy/sell advice. Details:

- Model: `ANTHROPIC_MODEL` (default `claude-opus-5-5`; `claude-haiku-5-5` is far cheaper for this
  short task). Effort `low`.
- For models that support it, the request opts into Anthropic's **server-side refusal fallback**
  (`fallbacks: "default"`), so a declined request is retried on a fallback model automatically.
- Results are cached in memory per identical metrics, so page refreshes don't re-bill.
- Any failure (bad key, rate limit, network, refusal) falls back to the rules with a short note.

Every response carries the disclaimer: informational only, not a prediction or personalised advice.

## Credentials

| Variable | Needed for | Required? |
|---|---|---|
| — | Everything in the core app | **None needed** |
| `ANTHROPIC_API_KEY` | Claude-written summary in insights | Optional — get one at <https://console.anthropic.com> |
| `UPSTOX_ACCESS_TOKEN` | Future Upstox adapter | Not used yet |

Secrets live only in `.env` on the backend (never in the frontend bundle). `.env` is git-ignored;
`.env.example` contains placeholders only.

---

## Tests

47 tests (`docker compose exec backend pytest`):

- **P&L math** — fees, weighted average cost, partial/full sells, realized P&L, insufficient cash at
  the exact boundary, insufficient holdings, invalid quantity/side, `total = realized + unrealized`
  identity over a mixed trade sequence, ledger replay, Indian number formatting.
- **Indicators** — SMA, RSI against a hand-computed Wilder value and extremes, annualised volatility.
- **Trading service (DB)** — cash/holding updates, rejections recorded without side effects,
  idempotent replay, unknown symbol.
- **API integration** — stocks → quote → history → preview → buy → replay → sell → oversell →
  portfolio reconciliation → transactions → orders → portfolio history → insights; `422`/`404` cases.
- **Insights** — rule triggers, determinism, LLM success/caching, connection error and refusal
  fallbacks, fallback parameter only for supported models (Anthropic client is mocked; no network).

## Known limitations

- Simulated prices; fixtures end on 23 Oct 2026 and don't advance by themselves (regenerate with
  `scripts.generate_fixtures --end YYYY-MM-DD`, then `scripts.seed`).
- Trading days are weekdays only — no NSE holiday calendar.
- Orders fill at the latest EOD close; no intraday prices, order types, slippage or market hours.
- Charges are a single configurable estimate, not real brokerage/taxes.
- Single implicit user/account; no authentication.
- The insights cache is in-process memory (reset on restart).
- The frontend proxy target (`BACKEND_URL`) is fixed when the frontend image is built.

## Out of scope for this milestone

Razorpay test payments (planned as an isolated module: plans, server-side order creation, signature
verification, webhook with event de-duplication), authentication/multi-user, real-time feeds, live
orders, price predictions, portfolio optimisation, scheduled jobs, deployment.

## License

MIT, see [LICENSE](LICENSE).
