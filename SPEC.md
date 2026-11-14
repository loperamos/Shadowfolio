# Wallet Sandbox — project spec

Working name. Drafted 2026-11-11 from the lessons of the first `investing-sandbox` prototype. This file describes *what* to build and *why*; it should change only when a decision changes.

## Goal

A hosted, subscription service where people test investing strategies against real market prices:

1. **Simulated wallets.** Every operation, whether entered by hand, imported or placed by an agent, is priced from real market data. The fill rules are visible.
2. **Import from any broker.** A reader per broker turns the user's exports into proposed operations; an LLM may cover brokers without their own reader. The app checks them, and the user confirms before anything is saved.
3. **Bring your own agent.** Users connect their own LLMs or agents over MCP or the API to operate wallets and read market information. Agents stay external: the service exposes the API but does not run them.
4. **Fair comparison.** Wallets, strategies and benchmarks such as SPY get the same deposits on the same dates. The app compares them on standard metrics.

## MVP scope

- US stocks and ETFs, long-only, fractional shares.
- Wallets in USD or EUR.
- Multi-user data model from day one: every wallet has an owner, even before login exists.
- Not in the MVP: plans and limits, billing, non-US exchanges, options, crypto, shorting, running agents for users.

## Core concepts

- **Wallet.** One kind only. A wallet is a cash balance plus a timeline of operations. It can be created empty, with starting cash, from an import, or as a copy of another wallet at a chosen time.
- **Operation.** Something that happened in a wallet at a timestamp: buy, sell, deposit, withdrawal, fee, dividend, split.
- **Order.** A request to buy or sell, placed now. The fill model turns it into an operation when market prices allow it.
- **Past operation.** A buy, sell, deposit or withdrawal entered at a past timestamp, such as "I bought 10 AAPL on 3 March at 14:32", or the question "what if I had sold here?". A real trade keeps what the broker reported: price, fees and, for a foreign-currency price, the amount settled in the wallet's currency. When no price is given, the fill model prices it from the historical data at that time. Inserting, editing or deleting one re-validates the whole timeline: no negative cash, and no selling shares that weren't held. An edit replaces the operation in a single check, so it never fails halfway, and an operation's type cannot change.
- **Fill model.** The rules that turn an order into a price: which price is used, market hours, fees and slippage. It never uses a price from after the order time.
- **Access tokens.** What a caller may do is decided by its token's scope, not by the type of wallet:
  - *owner* scope: everything the user can do in the UI, including past operations and imports. For example, the user's own agent can keep a wallet in sync with their real broker.
  - *trading* scope: read state and market data, and place or cancel orders **now only**, on the wallets it has been granted. Use this scope to evaluate an agent's strategy, so it cannot benefit from hindsight.
- **Hindsight label.** A wallet that received past operations after it was created is marked as such in comparisons, so results built with hindsight are never presented as forward-tested.

## Use cases

**User (web UI and HTTP API)**
1. Create, rename, copy or delete a wallet, choosing its currency and starting cash.
2. Import a broker statement: the app reads it and proposes operations, checks them, and the user confirms.
3. Add a past operation at a given time; the app checks or fills in its price.
4. Place or cancel an order now.
5. View a wallet: holdings, value over time, dividends and operations.
6. Copy a wallet at time T and change its history from there ("what if").
7. Compare wallets and benchmarks. Charts and metrics will be expanded after the MVP.
8. Create access tokens and grant them wallets. This only manages access; agents are not managed here.
9. *(To refine)* Create a rule strategy, such as monthly DCA or a fixed allocation with rebalancing, and backtest it.

**Agent (MCP)**
1. Read wallet state: cash, holdings, orders and value.
2. Read market information: quotes, price history up to now, dividends, company data.
3. Place or cancel orders now (trading scope).
4. Attach a short reason to each order, kept as a decision log.
5. With owner scope: record past operations and imports, for example to keep a wallet in sync with the user's real broker.

**System (scheduled jobs)**
1. Fill open orders.
2. Apply dividends and splits.
3. Save a daily value snapshot of each wallet.

## Market data

| Data | Covers | Used for |
| --- | --- | --- |
| **1-minute bars** (open, high, low, close and volume per minute) | The past | Pricing past operations, backtests, intraday charts |
| **Live prices, delayed** (for example by 15 minutes) | Now | Filling orders as they happen, current wallet values |
| **Daily bars** | Long ranges | Value over time, benchmark curves, comparisons |
| **Splits** | Corporate actions | Adjusting share counts and past views of a wallet |
| **Dividends** (amount, **currency**, ex-date, payment date) | Corporate actions | Automatic dividend credits |
| **FX rates**, daily | — | EUR wallets holding USD assets; converting dividends |
| **ISIN ↔ ticker** | — | Imports, since brokers often export ISINs |
| **Company data** (profile, sector, financial statements, ratios such as P/E) | — | Information for users and agents. After the MVP. |

**Fill model, first version:**
- A market order fills at the first price after the order time, such as the next minute bar's open, plus fees and slippage.
- A limit order fills only if a later bar reaches the limit price; until then it stays open.
- An order placed outside market hours waits for the next market open.

## Dividends (automatic)

1. Every day, fetch upcoming dividends for every security any wallet holds.
2. On the ex-date, record each wallet's shares. You must hold a share before the ex-date starts to qualify.
3. On the payment date, credit shares × amount, converted to the wallet's currency if needed.
4. Each payment is an operation linked to the provider's event ID, so it is never paid twice.

Decisions:
- **Withholding tax:** a rate per wallet (0% pays gross). Dividends show gross, tax and net; only the net reaches cash. Changing the rate works out every dividend again, and is refused if it takes away cash already spent. With accounts, a per-user default rate for new wallets.
- **Reinvestment:** reinvesting can be a per-wallet option.
- **Imported dividends:** match them to known events instead of crediting them twice.
- **Benchmarks:** they include dividends.

Lesson from the prototype: the provider **must** return dividend currency explicitly. A feed without it forced complex LLM research.

## Architecture

```text
interfaces/     web API (under /api) · MCP server · scheduler jobs      ← thin; call use cases
usecases/       use cases, grouped by area (wallets, history, valuation, market, ...)
domain/         wallets, operations, ledger (FIFO), fill model, valuation, metrics — pure, no I/O
ports/          interfaces the core depends on
adapters/       real implementations and fakes for every port
wiring/         one composition root per environment (test, local, production): the only place that picks adapters
web/            the React frontend; its API client is generated from the backend's OpenAPI schema
```

| Port | Gives the core | Adapters |
| --- | --- | --- |
| `PriceData` | Minute bars, daily bars, latest price | Fake (fixtures), Alpaca, cache of past daily closes (SQLite file) |
| `CorporateActions` | Dividends and splits | Fake, real provider |
| `CompanyData` | Profile and fundamentals (after the MVP) | Fake, real provider |
| `FxRates` | Daily rates | Fake, ECB, cache of past daily rates (SQLite file) |
| `SecurityLookup` | ISIN (and trading venue) → ticker | Fake, OpenFIGI |
| `StatementReader` | A broker's export → broker-neutral import records | DEGIRO (CSV) |
| `Clock` | "Now" | System clock, fixed clock, simulated clock (backtests) |
| `WalletRepository` | Persistence | In-memory, SQLite (Postgres later) |

Rules:
- The domain never does I/O and never reads the system time; time always comes from `Clock`.
- The whole app must run and be tested with fakes only. Each real adapter must pass the same contract tests as its fake.
- The web API and MCP call the same use cases; no business logic in interfaces.

Stack: Python with FastAPI and Pydantic; React with TypeScript, Vite and Mantine; Postgres (SQLite and in-memory repositories for local runs and tests). Docker images for deployment later.

## Hard parts

These get the most careful tests:
- **Time correctness:** the fill model, and never using a price from after the order or valuation time.
- **Splits and dividends** applied consistently to every past view of a wallet.
- **Import checks** before anything is saved.

## Data providers (to evaluate in the licensed-provider slice of the MVP plan)

The key requirement is the right to **display data to your own paying users**; personal plans almost never allow it. Prices are indicative as of 2026-11 and must be confirmed with each vendor in writing.

| Provider | Display to users | Indicative price | Notes |
| --- | --- | --- | --- |
| Databento | Yes: Equities Basic/Mini have no license fees | Usage-based plus subscription | Best licensing fit for US data |
| Marketdata.app | Yes: Commercial plan (vendor's claim) | ~$125–250/mo | Cheapest licensed option |
| Massive (ex-Polygon) | Business plans only | ~$2,499/mo, or Nasdaq Basic ~$0.45–0.90 per user/mo | Rich API, corporate actions, fundamentals |
| EODHD | Commercial license, quoted per case | From ~$399/mo | Global and EU coverage, fundamentals |
| Twelve Data | External display tier | ~$499/mo | Global |
| Tiingo | Redistribution sold separately | ~$250–500/mo (unconfirmed) | Cheap internal plans |
| Alpaca | No: redistribution not allowed | — | Fine for development only |
| ECB, OpenFIGI | Free | Free | FX and identifiers |

## Market notes

Existing products each cover one piece:
- **Trackers:** Sharesight, Ghostfolio.
- **Strategy builders and backtesters:** QuantConnect, Composer.
- **Broker paper accounts over MCP:** Alpaca, IBKR, tastytrade.
- **Agent trading demos:** Nof1 Alpha Arena.

None found combines a user's real wallet, their own agents and fair comparison in one broker-agnostic hosted service. Validate demand early.

## Legal

- Show a clear "not investment advice" disclaimer; the product is analysis and simulation.
- GDPR: user financial data and uploaded statements must be protected. If an LLM reads a statement, tell users it is sent to an LLM provider.
- Market-data display rights are covered under Data providers.

## MVP plan

Built as thin vertical slices: each one works end to end (API, use case, domain, storage and web) before the next starts.

Done:
- Skeleton: structure, AGENTS.md, tests, and CI for backend and web.
- Wallets: create, list, rename, duplicate and delete.
- History: deposits, withdrawals and past buys and sells at their real dates, with the broker's price, fees and settled amount; edit and delete; every change checked against the whole timeline.
- Valuation: latest prices (Alpaca, development only) and ECB rates, one total in the wallet's currency.
- Web: wallet list and wallet page with value, holdings and operations; sorting, filters and paging, kept in the URL.
- Cost basis and gains (FIFO lots).
- Past operations priced from market data when no price is given: minute bars and the first fill-model rule.
- Splits, then dividends (`CorporateActions`).
- Value over time: daily bars and historical FX, with gaps for days without a price, a period chosen by preset, dates or dragging, and past market data cached.
- Import, first broker: DEGIRO's Transactions and Account exports, with preview and confirm; tickers looked up by ISIN (OpenFIGI); fees, income, broker dividends and received shares as operations.

Next, in order:
5. Copy a wallet at time T.
6. Orders now: market and limit orders, the fill model and the order-filling job.
7. Comparison: benchmarks with the same deposits, metrics, charts, hindsight label.
8. MCP: tokens with owner and trading scopes, wallet grants, decision log.
9. Licensed data provider: trial the shortlisted providers against the contract tests and pick one.
10. Import: more brokers and operation types, with an LLM reader for brokers without their own.
11. Accounts, auth and hosting, then a public beta.

No paid subscription is needed before the licensed-provider slice.

## Open questions

- Rule strategies: how users define them, and what the rule language is.
- Withholding by the security's country (one rate per wallet while the MVP is US-only); dividend reinvestment option.
- Comparison metrics and charts beyond the basics.
- Plans, limits and pricing.
- Hosting provider.
- Instrument identity: key holdings by ISIN rather than ticker, so one security bought on different exchanges (e.g. Tesla on NASDAQ in USD and on Tradegate in EUR) is one holding; store the venue; value each holding from one listing (the US one in the MVP), converted with `FxRates`. Decide with the import or valuation slice.
- FX on real trades: the broker's settled amount is the source of truth for cash. Open: also accept an FX rate instead, and warn when a broker's rate is far from the market rate (brokers add a margin, e.g. DEGIRO's AutoFX).
- Currencies beyond USD and EUR (e.g. HKD listings) are rejected until market data covers those exchanges.
- Frontend ↔ backend in deployment: during local development the Vite dev server proxies API paths to the backend, so the browser sees one origin and the backend has no CORS setup. Decide with hosting whether the deployed frontend is served from the same origin (no CORS) or another one (CORS with explicit allowed origins).
- Serverless deployment (e.g. AWS Lambda for the backend, static hosting for the frontend, EventBridge Scheduler for the daily sync): production needs Postgres instead of SQLite (no lasting disk), with connection pooling (e.g. RDS Proxy) when many functions run at once.
- Protecting the sync entry point once the backend is public: authenticate the scheduler's calls, or have the scheduler invoke the function directly instead of over HTTP.
- Sync duration: HTTP gateways cut requests off after about 30 seconds and functions after minutes, so with many wallets the daily sync must run in batches (e.g. one queued job per wallet); the use case already works wallet by wallet.
