# Stock Compass — personal US stock recommender

A private, self-hosted tool that analyses US stocks every trading day, recommends which ones
to consider buying, **explains why in plain English**, and keeps every day's recommendations
in a local PostgreSQL database so you can check how well the model has actually done.

Before each US market open, a **LangGraph news agent** reads the latest articles and SEC filings
about the day's candidates, your holdings and every sector. An LLM (a free local model through Ollama,
or Claude) then writes a **morning brief** covering:

* **Picks:** evidence-backed picks with news sentiment and numbered links to the source articles.
* **Sectors:** which sectors deserve new money and why, backed by relative-strength data and news.
* **Exits:** add, hold, trim or exit advice for the stocks you already own.
* **Rupee view:** everything is framed for **an investor in India buying in INR**: the USD/INR trend, returns in rupees, FX costs and a rupee investment planner.

* **Free.** No paid APIs and no API keys. Market data comes from Yahoo Finance through the open-source [`yfinance`](https://github.com/ranaroussi/yfinance) library.
* **Private.** The database and APIs run only on your machine and are bound to `127.0.0.1`. The GitHub Pages site is just the dashboard's HTML/JS. It has no data in it.
* **Explainable.** Each pick has a score from 0 to 100, a breakdown into six factors, a list of reasons and cautions, a suggested position size and a suggested stop-loss.

> ⚠️ This is a rules-based research tool for personal use, not financial advice.

---

## Architecture — 5 services + 2 databases

```
            ┌──────────────────────────┐
 browser ──▶│ frontend (React, :3000)  │   also deployed to https://<you>.github.io/investment_recom
            └────────────┬─────────────┘   (static files only - calls YOUR localhost:8000)
                         │ REST
            ┌────────────▼─────────────┐      ┌───────────────────────────┐
            │ backend (FastAPI, :8000) │─────▶│ analytics (FastAPI, :8001)│
            │ • Yahoo Finance ingestion│ HTTP │ • indicators (SMA/RSI/MACD│
            │ • daily scheduler        │◀─────│   /ATR/vol/drawdown/Sharpe│
            │ • REST API for dashboard │      │ • market regime           │
            └────────────┬─────────────┘      │ • multi-factor scoring    │
                         │ SQL                │ • track-record evaluation │
            ┌────────────▼─────────────┐      │ (stateless, no DB, no net)│
            │ PostgreSQL 16 (:5432)    │      └───────────────────────────┘
            └──────────────────────────┘
```

| Layer | Folder | Responsibility |
|---|---|---|
| **Frontend** | [frontend/](frontend/) | Dashboard: today's picks, live quotes, per-stock charts, history, track record, methodology |
| **Backend** | [services/backend/](services/backend/) | Owns the database, downloads prices and fundamentals, runs the daily job and serves `/api/*` |
| **Analytics** | [services/analytics/](services/analytics/) | Pure maths: takes price data, returns scores, reasons, the market regime, sector rotation, exit signals, USD/INR stats and performance |
| **Clustering** | [services/clustering/](services/clustering/) | Social listening. Keeps its **own Postgres + pgvector** (`newsdb`). Ingests only new articles, saves each embedding once, clusters with UMAP + HDBSCAN, and has an LLM write a headline for new or changed clusters |
| **Agent** | [services/agent/](services/agent/) | LangGraph workflow: gathers news, filters it for trust and relevance, scores sentiment and has the LLM write cited reasoning |

### The morning-brief agent (LangGraph)

```
plan ─► gather_news  ×N in parallel (each candidate, holding, sector ETF, macro, USD/INR)
          │   Yahoo Finance + Finnhub + SEC EDGAR → dedupe → trust × relevance × recency → VADER sentiment
        join ─► analyze_pick    ×candidates ─┐   LLM: per-article sentiment, conviction, thesis,
             ├► analyze_exit    ×holdings   ─┼─► catalysts / risks with [n] citations
             └► analyze_sectors ×1          ─┘   (rules-based fallback if no LLM)
                                                  compose ─► brief stored in Postgres
```

* **News sources (free):**
  * [Yahoo Finance](https://finance.yahoo.com) headlines through yfinance (no key).
  * [SEC EDGAR](https://www.sec.gov/edgar): 8-K/10-Q/10-K filings and Form 4 insider buys and sells (no key). This is the most authoritative source.
  * [Finnhub](https://finnhub.io): wire-service company and market news. It needs a free key; without one, it is skipped.
* **Only trustworthy, relevant news is used.** Each publisher has a trust score (Reuters and the SEC at 1.0, content farms below the cut-off). An article must mention the company, and newer articles rank higher.
* **Links can't be made up.** The LLM only sees numbered articles (`[A3]`) and cites them by number. The agent then maps those numbers back to real URLs, and any citation to an article it wasn't given is dropped.
* **Verdicts:** each candidate's quant score is adjusted by ±8 points for news sentiment. The result is one of **Strong pick**, **Pick**, **Wait — news risk** (the numbers say buy but credible news argues for patience) or **Watch**.
* **Exit rules for your holdings** (they feed the LLM, and are used on their own if no LLM is available):
  * Exit signals: a 3×ATR trailing stop from the high since you bought, a confirmed downtrend, the model rating dropping to Avoid, a loss of more than 15%, or a bearish MACD crossover.
  * Trim: take partial profits when a position is up 30% or more and overbought.
  * Every signal is weighed against the reasons to hold.

### Database tables
`daily_prices` (OHLCV), `tickers` (name, sector, fundamentals), `recommendation_runs` (one row per market day, with the market regime) and `recommendations` (one row per stock per day: score, rating, components, metrics, reasons, cautions, weight and stop-loss).

---

## How a recommendation is made

1. **Collect.** Download 2 years of adjusted daily prices for about 65 liquid large caps and ETFs, plus SPY and ^VIX. Refresh fundamentals weekly.
2. **Read the market regime.** Combine three signals: SPY vs its 200-day average, the VIX level, and breadth (the share of stocks above their 200-day average). The result is **Risk-On / Neutral / Risk-Off**, which maps to a suggested equity exposure of **100% / 60% / 30%**.
3. **Score each stock** from 0 to 100 on six factors. Momentum, relative strength and risk are ranked against the other stocks on the same day.

   | Factor | Weight | What it measures |
   |---|---|---|
   | Trend | 25% | Price vs its 20/50/200-day averages, whether the 50-day is above the 200-day, and the 50-day's slope |
   | Momentum | 25% | 12-1 month, 6-month and 3-month returns (percentile rank) |
   | Relative strength | 15% | 6-month and 3-month return minus the S&P 500's |
   | Timing | 10% | RSI zone (overbought is penalised), MACD direction and crossovers, distance from the 52-week high |
   | Risk | 15% | Low volatility, shallow drawdown, high Sharpe ratio |
   | Fundamentals | 10% | Forward P/E, revenue growth, margin and leverage (neutral if the data is missing) |

4. **Rate the stock:** Strong Buy ≥ 78, Buy ≥ 65, Hold ≥ 45, otherwise Avoid. Two guard rails apply: a stock in a confirmed downtrend is capped at Hold, and a Risk-Off market downgrades Strong Buy to Buy.
5. **Size and protect each position.** The top picks get inverse-volatility weights scaled by the regime's exposure, and the rest stays in cash. The suggested stop-loss is the close minus 2 × ATR(14).
6. **Hold the model accountable.** The *Track record* page checks every past pick's return after 1 week, 1 month and 3 months against SPY, and whether higher ratings really did better.

---

### Social listening (clustering service)

```
backend news feed ──(cursor: only new rows)──► ingest ──► embed new articles only ──► pgvector (saved)
                                                         nomic-embed-text on the Mac GPU
window of last 14 days ──► UMAP 5-d ──► HDBSCAN ──► merge clusters with centroid cos ≥ 0.92 ──► UMAP 2-d map
changed clusters only ──► LLM headline + summary (cached by member hash) ──► Social page
```

* **Density-based clustering.** HDBSCAN (the DBSCAN family) finds stories without being told how many exist. Articles that match no story stay unclustered.
* **One story, one cluster.** Near-duplicate clusters are merged.
* **Stable ids.** A cluster keeps its id across runs when at least 30% of its articles overlap with a previous cluster.
* **Incremental.** A re-run with no new articles takes seconds: nothing is re-embedded or re-summarized.
* **GPU.** Docker on macOS can't reach the Apple GPU, so embeddings run through the native Ollama (Metal). To run on PyTorch **MPS** instead, set `CLUSTERING_URL=http://host.docker.internal:8003` in `.env`, run `docker compose up -d backend`, then `make social-native`.
* **Platform.** `platform` is stored for every item, so Twitter/X or LinkedIn connectors can be added later alongside News.

### Backtest (top 5 / 10 / 20 / 30)

Replays every stored recommendation day:
1. Buy the top N at the **next session's open**, with equal weights.
2. Rebalance daily, weekly or monthly.
3. Compare against SPY on the same dates.

For an Indian investor, `INR return = (1 + USD return) × (1 + USD/INR change) × (1 − FX markup)² − 1`, using a 1% markup each way by default. The currency move is either the actual USD/INR history or an assumed yearly rate. Every period and holding is shown, so the result can be audited.

### Transparency

The **Glossary** page defines every term and formula the dashboard uses (momentum, P/E, RSI, ATR, the INR maths, UMAP/HDBSCAN and so on). Every computed section also has a "How this is calculated" panel.

## Choosing the LLM

| `LLM_PROVIDER` in `.env` | Cost | Notes |
|---|---|---|
| `auto` (default) | free | Uses local Ollama if it's running, else Claude if `ANTHROPIC_API_KEY` is set, else rules-only |
| `ollama` | free | `brew install ollama && brew services start ollama && ollama pull qwen2.5:7b` (~4.7 GB). Runs on the Mac's GPU; a brief takes ~5–10 min |
| `anthropic` | paid per use | Set `ANTHROPIC_API_KEY`. The default model `claude-opus-5` gives the best reasoning (roughly $1–2 per daily brief); set `ANTHROPIC_MODEL=claude-haiku-4-5` for a much cheaper brief |
| `none` | free | Template-based reasoning from the same data and news |

Ollama runs natively on the Mac, not in Docker, so it can use the GPU. The agent container reaches it at `host.docker.internal:11434`.

## Run it locally

Prerequisites: Docker Desktop (running), `make`, and `curl`. Optional: Ollama (see above) and a free Finnhub key.

```bash
make up          # builds and starts db + analytics + backend + frontend
open http://localhost:3000
```

On first start the backend downloads the data, runs today's analysis, then **backfills 60 past
trading days** so history and the track record fill in straight away. This takes 1–3 minutes.
The connection indicator in the top-right corner shows progress.

After that, as long as Docker is running, it runs automatically:
* **07:30 New York time on weekdays** (17:00 IST in the US summer, 18:00 in winter): the pre-market **morning brief**, with fresh prices, re-scoring, news and exit reviews.
* **17:00 New York time on weekdays:** the close-of-day re-score that goes into history and the track record.
If your laptop was asleep, the job catches up when Docker starts again.

| Command | What it does |
|---|---|
| `make run` | Analyse now (for example during market hours) |
| `make brief` | Run the news agent and write today's morning brief now |
| `make sweep` | Collect news for every tracked stock, then re-cluster |
| `make cluster` | Re-run social-listening clustering (new articles only) |
| `make backfill DAYS=250` | Replay the model over more history |
| `make backup` | Save a `pg_dump` to `backups/` (git-ignored) |
| `make psql` | Open a SQL shell |
| `make logs` / `make down` | Follow the logs / stop everything (your data stays in the `pgdata` volume) |
| `make dev-frontend` | Run the dashboard with hot reload on :5173 |

API docs: http://localhost:8000/docs · Configuration: copy [.env.example](.env.example) to `.env` (to set your own watchlist, top-N, schedule and so on).

---

## GitHub Pages deployment

[.github/workflows/deploy-pages.yml](.github/workflows/deploy-pages.yml) builds the dashboard and publishes it to
`https://manujmehrotra.github.io/investment_recom/` whenever `frontend/` changes on `main`.
[.github/workflows/ci.yml](.github/workflows/ci.yml) runs the Python tests, builds the frontend and builds the Docker images on every push and pull request.

**One-time setup:** in the repo on GitHub, open **Settings → Pages → Build and deployment → Source** and choose **GitHub Actions**.

### What is (and isn't) public
* The site contains **only static code**. No recommendations, prices or database content are ever uploaded.
* When you open the site, your browser calls `http://localhost:8000`, which is **your own machine**. Anyone else who opens the URL gets "Backend offline", because their computer isn't running your backend.
* **The repository itself is public**, so the source code is visible. On a free GitHub plan, Pages requires a public repo. If you want the code private too, either make the repo private and use only `http://localhost:3000` (Docker), or upgrade to GitHub Pro.
* The site sends `noindex` and `robots.txt` disallow headers so search engines skip it.

### Browser notes
* **Chrome / Edge:** the first time, the browser asks to allow the page to access devices on your local network. Click **Allow**. The backend already sends the required `Access-Control-Allow-Private-Network` header.
* **Safari** may block an HTTPS page from calling `http://localhost`. If it does, use `http://localhost:3000`.
* If your GitHub username or the repo name differs, add the Pages origin to `CORS_ORIGINS` in `.env`.

---

## Development

```bash
# analytics
cd services/analytics && python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt && pytest && uvicorn app.main:app --port 8001

# backend (tests use SQLite, so no Postgres is needed)
cd services/backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt && pytest
DATABASE_URL=postgresql+psycopg://invest:invest@localhost:5432/invest uvicorn app.main:app --port 8000

# frontend
cd frontend && npm install && npm run dev
```

## Limitations to keep in mind
* Yahoo data is free but unofficial. It is delayed by about 15 minutes, and Yahoo can rate-limit or change it without notice.
* Backfilled days use price data only (no fundamentals) so they don't peek at information from the future. The fundamentals themselves are today's snapshot.
* The universe is fixed (about 65 large caps), so the results carry survivorship bias. Don't treat a short track record as proof of anything. Momentum-style models are known to go through multi-month stretches of underperformance.
