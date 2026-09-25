// Every formula here matches the code in services/*/app. If you change a calculation, change it here too.

export interface Term {
  term: string;
  aka?: string;
  category: Category;
  what: string;
  formula?: string;
  example?: string;
  read?: string; // how to interpret
  usedIn?: string;
}

export type Category =
  | "Prerequisites"
  | "Price & trend"
  | "Momentum & strength"
  | "Risk"
  | "Valuation & fundamentals"
  | "Model & ratings"
  | "Market regime & sectors"
  | "Positions & exits"
  | "News & sentiment"
  | "Rupee investing"
  | "Measuring results"
  | "Clustering & social listening";

export const CATEGORIES: Category[] = [
  "Prerequisites",
  "Price & trend",
  "Momentum & strength",
  "Risk",
  "Valuation & fundamentals",
  "Model & ratings",
  "Market regime & sectors",
  "Positions & exits",
  "News & sentiment",
  "Rupee investing",
  "Measuring results",
  "Clustering & social listening",
];

export const GLOSSARY: Term[] = [
  // ---------------------------------------------------------------- prerequisites
  { term: "Stock / share", category: "Prerequisites", what: "A small ownership slice of a company. Its price moves with what investors expect the company to earn." },
  { term: "Ticker", category: "Prerequisites", what: "The short code a stock trades under on the exchange, e.g. AAPL = Apple Inc., BRK-B = Berkshire Hathaway class B." },
  { term: "ETF", aka: "Exchange-traded fund", category: "Prerequisites", what: "A fund that trades like a stock and holds a basket of stocks. XLK holds US technology companies; QQQ holds the Nasdaq-100; GLD tracks gold.", read: "ETFs have no earnings of their own, so their fundamentals score is neutral (50)." },
  { term: "S&P 500 and SPY", category: "Prerequisites", what: "The S&P 500 is an index of ~500 large US companies - the usual yardstick for 'the market'. SPY is the ETF that tracks it; every comparison here is against SPY.", usedIn: "Benchmark everywhere" },
  { term: "Open, close, adjusted prices", category: "Prerequisites", what: "Open = first traded price of the day, close = last. Prices here are adjusted for splits and dividends so returns over time are comparable.", usedIn: "All calculations; backtests buy at the open" },
  { term: "Trading day", category: "Prerequisites", what: "A day the US market is open. There are about 252 per year, 21 per month and 63 per quarter - which is why formulas use 21, 63, 126 and 252.", example: "'3-month return' = change over the last 63 trading days." },
  { term: "Return", category: "Prerequisites", what: "How much a price changed, as a fraction of where it started.", formula: "return = price_end / price_start − 1", example: "$100 → $112 = 112/100 − 1 = +12%." },
  { term: "Percentage points vs percent", category: "Prerequisites", what: "If a stock returned 15% and the S&P returned 10%, it beat the market by 5 percentage points (not by 50%).", usedIn: "'Outperforming the S&P 500 by 8.2 pts'" },
  { term: "Market capitalisation (size buckets)", aka: "market cap", category: "Prerequisites", what: "Total value of a company's shares.", formula: "market cap = share price × shares outstanding", read: "Mega ≥ $200B · Large $10–200B · Mid $2–10B · Small $300M–2B · Micro < $300M. Buckets are assigned from live Yahoo data.", usedIn: "Size filter on Picks" },
  { term: "Sector", category: "Prerequisites", what: "The industry group a company belongs to (Technology, Healthcare, Energy …) as reported by Yahoo Finance. Each sector is benchmarked with a SPDR sector ETF (XLK, XLV, XLE …).", usedIn: "Sector filter, Sectors page" },

  // ---------------------------------------------------------------- price & trend
  { term: "Simple moving average", aka: "SMA, 50-day / 200-day average", category: "Price & trend", what: "The average closing price over the last n days - smooths out daily noise to show the trend.", formula: "SMA_n = (P_t + P_t−1 + … + P_t−n+1) / n", read: "Price above its 200-day = long-term uptrend. Above the 50-day = medium-term strength.", usedIn: "Trend score, stock charts, exit rules" },
  { term: "Golden cross / death cross", category: "Price & trend", what: "50-day average crossing above (golden) or below (death) the 200-day average.", read: "The model treats '50-day above 200-day' as an established uptrend and 'price and 50-day both below the 200-day' as a confirmed downtrend (rating capped at Hold)." },
  { term: "Exponential moving average", aka: "EMA", category: "Price & trend", what: "A moving average that weights recent days more.", formula: "EMA_t = α·P_t + (1 − α)·EMA_t−1,  α = 2 / (span + 1)", usedIn: "MACD" },
  { term: "52-week high distance", category: "Price & trend", what: "How far the price is below its highest close of the last year.", formula: "distance = P_t / max(P over 252 days) − 1", read: "Within 5% of the high earns timing points (+10); more than 30% below loses points (−10)." },
  { term: "Trend score", category: "Price & trend", what: "Points for trend conditions, out of 100.", formula: "30 if price > SMA200 · 20 if price > SMA50 · 25 if SMA50 > SMA200 · 15 if SMA50 rising over 20 days · 10 if price > SMA20", usedIn: "25% of the model score" },

  // ---------------------------------------------------------------- momentum
  { term: "Momentum", aka: "12-1 month momentum", category: "Momentum & strength", what: "The tendency of stocks that rose over the past 3–12 months to keep outperforming for a while. The 12-1 version skips the most recent month, which tends to reverse.", formula: "12-1 momentum = P_t−21 / P_t−252 − 1   (price 1 month ago ÷ price 12 months ago − 1)", example: "Price 12 months ago $100, 1 month ago $140 → +40%, regardless of the last month.", read: "Momentum is ranked against the other stocks on the same day (see Percentile rank).", usedIn: "Momentum score (25%), reasons" },
  { term: "Momentum score", category: "Momentum & strength", what: "Average percentile rank of three horizons.", formula: "100 × mean( pct_rank(12-1 month), pct_rank(6-month), pct_rank(3-month) )", example: "Top 10% on 12-1 month, 80th percentile on 6m and 3m → 100 × (0.9 + 0.8 + 0.8)/3 ≈ 83." },
  { term: "Percentile rank", aka: "cross-sectional rank", category: "Momentum & strength", what: "Where a stock stands relative to all stocks analysed that day, from 0 (worst) to 1 (best). Missing values are placed at the median (0.5).", read: "Percentiles make the model adapt to the market: in a strong year a +20% stock may still be average." },
  { term: "Relative strength", aka: "RS vs S&P 500", category: "Momentum & strength", what: "A stock's return minus the S&P 500's return over the same window.", formula: "RS_6m = return_6m(stock) − return_6m(SPY)", example: "Stock +18%, SPY +10% → RS = +8 pts.", usedIn: "Relative-strength score (15%): 100 × mean(pct_rank(RS_6m), pct_rank(RS_3m))" },
  { term: "RSI", aka: "Relative Strength Index (14-day)", category: "Momentum & strength", what: "A 0–100 gauge of recent buying vs selling pressure (Wilder's method).", formula: "RS = avg gain / avg loss over 14 days (Wilder smoothing, α = 1/14);  RSI = 100 − 100 / (1 + RS)", read: "> 70 overbought, < 30 oversold. The model likes 45–65 (+20), penalises > 75 (−25), and treats 30–45 inside an uptrend as a pullback entry (+15).", usedIn: "Timing score, stock page chart" },
  { term: "MACD", aka: "Moving average convergence divergence", category: "Momentum & strength", what: "Difference between a fast and a slow EMA - shows momentum turning.", formula: "MACD = EMA12 − EMA26;  signal = EMA9(MACD);  histogram = MACD − signal", read: "Histogram > 0 = upward momentum (+15). A bullish crossover (histogram turning positive within 5 days) adds +10.", usedIn: "Timing score, exit rules" },
  { term: "Volume ratio", category: "Momentum & strength", what: "Recent trading volume vs normal.", formula: "avg volume 20 days / avg volume 60 days", read: "> 1.3 while rising = institutional buying interest (shown as a reason)." },

  // ---------------------------------------------------------------- risk
  { term: "Volatility (annualised)", category: "Risk", what: "How much the price swings day to day, scaled to a year.", formula: "σ = stdev(daily log returns over 63 days) × √252", example: "Daily stdev 1.5% → 1.5% × 15.9 ≈ 24% a year.", read: "> 50% = expect big swings; the position size is cut accordingly." },
  { term: "Maximum drawdown", category: "Risk", what: "The worst peak-to-trough fall in the last year.", formula: "max drawdown = min over the year of ( P_t / highest price so far − 1 )", example: "Peak $120, later low $84 → −30%." },
  { term: "Sharpe ratio", category: "Risk", what: "Return per unit of risk.", formula: "Sharpe = mean(daily return) / stdev(daily return) × √252   (risk-free rate taken as 0)", read: "> 1 good, > 1.5 excellent." },
  { term: "Risk score", category: "Risk", what: "Rewards calm, resilient stocks relative to peers.", formula: "100 × ( 0.5·pct_rank(low volatility) + 0.3·pct_rank(shallow drawdown) + 0.2·pct_rank(Sharpe) )", usedIn: "15% of the model score" },
  { term: "ATR", aka: "Average True Range (14-day)", category: "Risk", what: "Typical daily price range in dollars, including overnight gaps.", formula: "TR = max(high − low, |high − prev close|, |low − prev close|);  ATR = Wilder average of TR over 14 days", usedIn: "Stop-loss and trailing stop" },
  { term: "VIX", category: "Risk", what: "The market's 'fear gauge': expected S&P 500 volatility over the next 30 days, from options prices.", read: "< 20 calm · 20–25 moderate · > 25 fearful." },

  // ---------------------------------------------------------------- valuation
  { term: "P/E ratio (trailing)", aka: "price-to-earnings", category: "Valuation & fundamentals", what: "How many dollars investors pay for each dollar of the company's profit over the last 12 months.", formula: "trailing P/E = share price / earnings per share (last 12 months)", example: "Price $150, EPS $6 → P/E 25: you pay 25 years of current profit.", read: "High P/E = investors expect growth (or the stock is expensive). Negative or missing when the company loses money." },
  { term: "Forward P/E", category: "Valuation & fundamentals", what: "Same idea using analysts' expected earnings for the next 12 months (from Yahoo Finance).", formula: "forward P/E = share price / expected EPS (next 12 months)", read: "Model points: 0–25 → full marks; 25–40 → 0.6; > 40 → 0.25; negative → 0. Reasons flag > 40 as 'expensive'.", usedIn: "Fundamentals score" },
  { term: "EPS", aka: "Earnings per share", category: "Valuation & fundamentals", what: "Net profit divided by the number of shares.", formula: "EPS = net income / shares outstanding" },
  { term: "Revenue growth", category: "Valuation & fundamentals", what: "Year-over-year change in sales (most recent quarter vs a year earlier, from Yahoo).", read: "> 15% → full marks; 5–15% → 0.75; 0–5% → 0.5; shrinking → 0.15." },
  { term: "Profit margin", category: "Valuation & fundamentals", what: "Share of revenue kept as profit.", formula: "profit margin = net income / revenue", read: "> 20% → full marks; 10–20% → 0.75; > 0 → 0.5; loss → 0.1." },
  { term: "Debt-to-equity", category: "Valuation & fundamentals", what: "Borrowing relative to shareholders' money. Yahoo reports it in percent (150 = 1.5×).", read: "< 50 → full marks; 50–150 → 0.6; > 150 → 0.3." },
  { term: "Fundamentals score", category: "Valuation & fundamentals", what: "Average of the four items above that are available, × 100. If none are available (ETFs, data gaps), it is neutral 50 rather than a penalty.", usedIn: "10% of the model score. Backfilled history uses no fundamentals (they would be today's numbers - look-ahead bias)." },

  // ---------------------------------------------------------------- model
  { term: "Model score", category: "Model & ratings", what: "The weighted sum of the six component scores (each 0–100).", formula: "score = 0.25·trend + 0.25·momentum + 0.15·relative strength + 0.10·timing + 0.15·risk + 0.10·fundamentals", usedIn: "Ranking on Picks" },
  { term: "Timing score", category: "Model & ratings", what: "Short-term entry quality. Starts at 50, then RSI zone, MACD direction and crossover, and 52-week-high distance add or subtract points; clipped to 0–100." },
  { term: "Ratings", category: "Model & ratings", what: "Strong Buy ≥ 78 · Buy ≥ 65 · Hold ≥ 45 · Avoid below. Cut-offs are absolute, so a weak market produces fewer buys.", read: "Guard rails: a confirmed downtrend caps the rating at Hold; a Risk-Off market downgrades Strong Buy to Buy." },

  // ---------------------------------------------------------------- regime & sectors
  { term: "Market breadth", category: "Market regime & sectors", what: "Share of tracked stocks trading above their own 200-day (or 50-day) average.", read: "≥ 55% broad participation; < 40% weak." },
  { term: "Market regime", category: "Market regime & sectors", what: "Risk-On / Neutral / Risk-Off from three signals: SPY vs its 200-day average, VIX level, and breadth.", formula: "Risk-On: 2+ bullish signals and none bearish · Risk-Off: 2+ bearish (or SPY below its 200-day with nothing bullish) · otherwise Neutral", read: "Suggested equity exposure 100% / 60% / 30%; the rest in cash." },
  { term: "Sector rotation quadrant", category: "Market regime & sectors", what: "Where a sector sits vs the S&P 500, using 3-month RS as level and 1-month RS as direction.", formula: "Leading: RS3m ≥ 0 and RS1m ≥ 0 · Weakening: RS3m ≥ 0, RS1m < 0 · Improving: RS3m < 0, RS1m ≥ 0 · Lagging: both < 0" },
  { term: "Sector strength", category: "Market regime & sectors", what: "Score used to rank sectors.", formula: "100 × ( 0.35·pct_rank(RS 3m) + 0.25·pct_rank(RS 1m) + 0.20·avg model score of its stocks/100 + 0.20·share above 50-day )" },

  // ---------------------------------------------------------------- positions
  { term: "Inverse-volatility weight", category: "Positions & exits", what: "Suggested share of your money per pick: calmer stocks get more.", formula: "w_i = (1/σ_i) / Σ(1/σ_j) × regime exposure   (σ floored at 5%; 30% if unknown)", example: "Two picks at 20% and 40% volatility → 67% / 33% before the regime scaling." },
  { term: "Stop-loss (suggested)", category: "Positions & exits", what: "A price at which to reconsider a new position.", formula: "stop = latest close − 2 × ATR14" },
  { term: "Trailing stop (holdings)", aka: "chandelier exit", category: "Positions & exits", what: "Follows the price up and never down.", formula: "trailing stop = highest close since you bought − 3 × ATR14", read: "A close below it is the strongest exit signal (+3 exit points)." },
  { term: "Exit / hold points", category: "Positions & exits", what: "Rule tally behind Add / Hold / Trim / Exit for your holdings.", formula: "Exit points: trailing stop hit +3 · confirmed downtrend +3 (or below 200-day +1) · below 50-day +1 · rated Avoid +2 · down > 15% +1 · bearish MACD cross +1.  Hold points: uptrend +2 · rated Buy/Strong Buy +2 · beating S&P over 6m +1 · near 52-week high +1", read: "≥ 4 exit points → Exit; ≥ 2 (or up ≥ 30% with RSI > 75) → Trim; ≥ 4 hold points + Strong Buy + not extended → Add; else Hold." },

  // ---------------------------------------------------------------- news
  { term: "Source trust", category: "News & sentiment", what: "A reputation weight per publisher: SEC EDGAR and Reuters 1.0, CNBC 0.95, Yahoo Finance 0.85 … content farms below 0.4 are dropped.", usedIn: "Filtering and ranking articles" },
  { term: "Relevance", category: "News & sentiment", what: "1.0 if the headline names the company or ticker; 0.75 if only the summary does; 0.4 (dropped) otherwise. Filings are always 1.0." },
  { term: "Article rank", category: "News & sentiment", what: "Which articles the agent reads first.", formula: "rank = trust × relevance × e^(−age in days / 3)", example: "A 1-day-old Reuters headline naming the company: 1.0 × 1.0 × 0.72 = 0.72." },
  { term: "VADER sentiment", category: "News & sentiment", what: "A fast, rule-based lexicon score from −1 (negative) to +1 (positive), extended with finance words (beat, downgrade, probe, surge …).", read: "Baseline for every article; shown as '(lexicon)'." },
  { term: "LLM sentiment", category: "News & sentiment", what: "The language model's per-article read of the impact on the stock, −1 to +1, shown as '(AI)'. Replaces VADER when available." },
  { term: "News sentiment (per stock)", category: "News & sentiment", what: "Trust- and recency-weighted average of article sentiment (or the LLM's overall judgement).", formula: "Σ sentiment_i × rank_i / Σ rank_i" },
  { term: "News-adjusted score and verdict", category: "News & sentiment", what: "How the brief combines numbers and news.", formula: "adjusted = model score + 8 × news sentiment.  Wait — news risk: buy-rated but news ≤ −0.3 (or the AI says Avoid) · Strong pick: Strong Buy, news ≥ −0.1, conviction High/Medium · Pick: other buy-rated · Watch: not buy-rated" },
  { term: "Insider trade (Form 4)", category: "News & sentiment", what: "Executives and directors must report their trades to the SEC. Open-market purchases are a stronger signal (+0.5) than sales (−0.15), which are often pre-planned." },
  { term: "8-K red flags", category: "News & sentiment", what: "SEC current-report items that often mean trouble: 1.05 cyber incident, 2.05 restructuring, 2.06 impairment, 3.01 delisting notice, 4.01 auditor change, 4.02 restated financials (sentiment −0.5)." },

  // ---------------------------------------------------------------- INR
  { term: "USD/INR", category: "Rupee investing", what: "Rupees per US dollar. If it rises, the dollar strengthened and the rupee weakened.", example: "85 → 92 means each dollar you hold is worth ₹7 more." },
  { term: "Return in rupees", category: "Rupee investing", what: "What an India-based investor actually earns.", formula: "INR return = (1 + USD return) × (1 + USD/INR change) × (1 − FX markup)² − 1", example: "Stocks +10%, rupee weakens 3%, 1% markup each way: 1.10 × 1.03 × 0.99² − 1 = +11.0%.", usedIn: "Brief, Portfolio, Backtest" },
  { term: "FX markup", category: "Rupee investing", what: "The spread your bank or broker charges to convert rupees to dollars and back. Default assumption: 1% each way (set FX_MARKUP_PCT).", read: "A round trip costs ~2%, so frequent in-and-out trading is expensive for INR investors." },
  { term: "FX effect on a holding", category: "Rupee investing", what: "The part of your rupee gain caused purely by the currency.", formula: "FX gain (₹) = shares × avg cost ($) × (today's USD/INR − USD/INR when bought)" },
  { term: "LRS and TCS", category: "Rupee investing", what: "Indian residents remit money abroad under the Liberalised Remittance Scheme (currently up to US$250,000 per financial year). Tax Collected at Source may apply above an annual threshold and can be claimed back against tax. Foreign-share gains and US dividend withholding have their own tax rules.", read: "Rules change with budgets - confirm with a CA." },

  // ---------------------------------------------------------------- results
  { term: "Forward return", category: "Measuring results", what: "What a pick returned after it was recommended: from that day's close to the close 5, 21 or 63 sessions later.", usedIn: "Track record" },
  { term: "Excess return", category: "Measuring results", what: "Forward return minus SPY's return over the same days.", formula: "excess = return(pick) − return(SPY)" },
  { term: "Win rate / hit rate", category: "Measuring results", what: "Share of picks (or backtest periods) with a positive return. 'Beat SPY' = share with a positive excess return." },
  { term: "Top-N backtest", category: "Measuring results", what: "Replays stored recommendations: on each rebalance date buy the top N at the next open, equal weight, hold to the next rebalance.", formula: "period return = mean over holdings of (exit open / entry open − 1);  equity = Π (1 + period return − trading cost)", usedIn: "Backtest page" },
  { term: "Annualised return", aka: "CAGR", category: "Measuring results", what: "The yearly rate that compounds to the total return.", formula: "CAGR = (1 + total return)^(1 / years) − 1", read: "Only shown once there is at least 1 year of history - annualising a few months exaggerates wildly." },
  { term: "Turnover", category: "Measuring results", what: "Share of the portfolio replaced at a rebalance; trading cost is charged on it." },
  { term: "Look-ahead and survivorship bias", category: "Measuring results", what: "Look-ahead: using information you would not have had at the time (why backfills skip fundamentals). Survivorship: the universe is today's companies, so failed ones are missing - real results would be somewhat worse." },

  // ---------------------------------------------------------------- clustering
  { term: "Embedding", category: "Clustering & social listening", what: "A list of numbers (768 here, from nomic-embed-text) that captures an article's meaning, so similar stories get similar vectors. Computed once per article and saved in the social database (pgvector).", usedIn: "Social listening" },
  { term: "Cosine similarity", category: "Clustering & social listening", what: "How aligned two embeddings are, from −1 to 1.", formula: "cos(a, b) = (a · b) / (|a| |b|)", example: "Two headlines about Nvidia's earnings ≈ 0.88; Nvidia vs an oil story ≈ 0.49." },
  { term: "UMAP", category: "Clustering & social listening", what: "A dimensionality-reduction method that keeps neighbourhoods intact. Used twice: to 5 dimensions for clustering, and to 2 dimensions for the map.", read: "On the map, closeness means similar meaning; absolute positions and distances between far-apart groups are not meaningful." },
  { term: "HDBSCAN", aka: "density-based clustering (DBSCAN family)", category: "Clustering & social listening", what: "Finds dense groups of points = stories. Unlike k-means you don't choose the number of clusters, and unlike DBSCAN you don't tune a distance 'eps'. Articles that fit no story are left as noise.", read: "min cluster size 3: a story needs at least three articles." },
  { term: "Duplicate-story merge", category: "Clustering & social listening", what: "Clusters whose mean embeddings have cosine similarity ≥ 0.92 are merged, so one story appears as exactly one cluster." },
  { term: "Keywords (c-TF-IDF)", category: "Clustering & social listening", what: "Words that are frequent in one cluster but rare in others (TF-IDF computed per cluster)." },
  { term: "Stable cluster id", category: "Clustering & social listening", what: "A cluster keeps its id across runs when it shares ≥ 30% of its articles (Jaccard overlap) with a previous cluster; its headline is regenerated only when its members change." },
];
