// The dashboard is a static site; all data comes from YOUR backend on your own machine.
// Nothing is ever sent anywhere else, even when the page is served from GitHub Pages.

export type Rating = "Strong Buy" | "Buy" | "Hold" | "Avoid";

export type CapCategory = "Mega" | "Large" | "Mid" | "Small" | "Micro" | "ETF";

export interface Recommendation {
  symbol: string;
  name: string | null;
  sector: string | null;
  cap_category: CapCategory | null;
  market_cap: number | null;
  rank: number;
  score: number;
  rating: Rating;
  price: number;
  stop_loss: number | null;
  target_weight: number | null;
  components: Record<string, number>;
  metrics: Record<string, number | boolean | null>;
  reasons: string[];
  cautions: string[];
  run_date?: string;
}

export interface Regime {
  label: "Risk-On" | "Neutral" | "Risk-Off";
  equity_exposure: number;
  summary: string;
  metrics: Record<string, number | null>;
}

export interface Run {
  run_date: string;
  source: string;
  created_at: string | null;
  model_version: string;
  regime: Regime;
  universe_size: number;
  skipped: Record<string, string>;
  recommendations: Recommendation[];
}

export interface RunSummary extends Omit<Run, "recommendations"> {
  top_picks: string[];
  top_pick_names: Record<string, string>;
  buy_count: number;
}

export interface JobStatus {
  running: boolean;
  task: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  message: string;
}

export interface Health {
  status: string;
  database: string;
  analytics: { status: string; model_version?: string };
  price_rows: number;
  last_market_date: string | null;
  job: JobStatus;
  next_scheduled_run: string | null;
  next_brief: string | null;
  last_brief_date: string | null;
  agent: { status: string; llm_provider?: string; llm_model?: string; news_sources?: Record<string, boolean> };
}

export interface Quote {
  price: number;
  prev_close: number;
  change: number;
  change_pct: number | null;
  as_of: string;
}

export interface StockDetail {
  symbol: string;
  info: Record<string, string | number | null>;
  indicators: {
    dates: string[];
    close: (number | null)[];
    sma50: (number | null)[];
    sma200: (number | null)[];
    rsi14: (number | null)[];
    macd_hist: (number | null)[];
  };
  latest: Recommendation | null;
  news: NewsItem[];
  history: { run_date: string; score: number; rating: Rating; rank: number }[];
}

export interface HorizonStats {
  n: number;
  avg_return: number | null;
  hit_rate: number | null;
  avg_excess: number | null;
  beat_benchmark_rate: number | null;
}

export interface Performance {
  horizons: string[];
  summary: ({ group: string; count: number } & Record<string, HorizonStats | string | number>)[];
  rows: ({ run_date: string; symbol: string; name: string | null; rating: Rating; score: number; entry_price: number } & Record<string, number | string | null>)[];
}

export interface Methodology {
  model_version: string;
  weights: Record<string, number>;
  rating_thresholds: { min_score: number; rating: Rating }[];
  components: Record<string, string>;
  rules: string[];
  regime: string;
  universe: string[];
  benchmark: string;
  data_source: string;
  schedule: string;
}

export interface NewsItem {
  id: string;
  publisher: string;
  title: string;
  url: string;
  kind: "news" | "filing" | "insider";
  published_at: string;
  sentiment: number | null;
  sentiment_method: "vader" | "llm" | "filing-rule" | null;
  takeaway: string | null;
  trust?: number;
  source_api?: string;
}

export interface Fx {
  pair: string;
  rate: number;
  as_of: string;
  ret_1w: number | null;
  ret_1m: number | null;
  ret_3m: number | null;
  ret_6m: number | null;
  ret_1y: number | null;
  cagr: number | null;
  cagr_years: number;
  volatility_1y: number | null;
  sma200: number | null;
  trend: string;
  markup_pct: number;
}

export type Verdict = "Strong pick" | "Pick" | "Wait - news risk" | "Watch";

export interface BriefPick {
  symbol: string;
  name: string | null;
  sector: string | null;
  cap_category: CapCategory | null;
  rank: number;
  score: number;
  rating: Rating;
  price: number;
  target_weight: number | null;
  stop_loss: number | null;
  method: "llm" | "rules";
  conviction: "High" | "Medium" | "Low" | "Avoid";
  thesis: string;
  catalysts: string[];
  risks: string[];
  evidence: NewsItem[];
  articles: NewsItem[];
  news_sentiment: number | null;
  vader_sentiment: number | null;
  sentiment_label: string;
  adjusted_score: number;
  verdict: Verdict;
}

export type ExitAction = "Add" | "Hold" | "Trim" | "Exit";

export interface ExitAdvice {
  symbol: string;
  method: "llm" | "rules";
  action: ExitAction;
  quant_action: ExitAction | null;
  confidence: "High" | "Medium" | "Low";
  rationale: string;
  reasons_to_exit: string[];
  reasons_to_hold: string[];
  news_sentiment: number | null;
  sentiment_label: string;
  evidence: NewsItem[];
  articles: NewsItem[];
  signal: { trailing_stop?: number | null; exit_points?: number; hold_points?: number; rating?: Rating | null; score?: number | null };
  brief_date?: string;
}

export interface SectorRow {
  sector: string;
  etf: string;
  rank: number;
  strength: number;
  quadrant: "Leading" | "Weakening" | "Improving" | "Lagging" | "Unknown";
  ret_1w: number | null;
  ret_1m: number | null;
  ret_3m: number | null;
  rs_1m: number | null;
  rs_3m: number | null;
  above_sma200: boolean;
  breadth_50: number | null;
  avg_score: number | null;
  stock_count: number;
  buy_count: number;
  top_symbols: string[];
  stance: "Overweight" | "Neutral" | "Underweight";
  rationale: string;
  evidence: NewsItem[];
  news_sentiment: number | null;
}

export interface Brief {
  brief_date: string;
  run_date: string;
  as_of: string;
  generated_at: string;
  llm: { provider: string; model: string };
  regime: Regime;
  fx: Fx | Record<string, never>;
  market: {
    method: "llm" | "rules";
    headline: string;
    market_narrative: string;
    key_risks: string[];
    inr_investor_note: string;
    evidence: NewsItem[];
    sectors: SectorRow[];
  };
  picks: BriefPick[];
  exits: ExitAdvice[];
  stats: { articles: number; by_source: Record<string, number>; finnhub_enabled: boolean };
  errors: string[];
}

export interface BriefSummary {
  brief_date: string;
  run_date: string;
  llm: string;
  headline: string | null;
  strong_picks: string[];
  articles: number;
}

export interface HoldingRow {
  id: number;
  symbol: string;
  name: string | null;
  sector: string | null;
  quantity: number;
  avg_cost: number;
  buy_date: string | null;
  buy_fx_rate: number | null;
  buy_fx_is_estimate: boolean;
  notes: string | null;
  price: number | null;
  cost_usd: number;
  value_usd: number | null;
  pnl_usd: number | null;
  pnl_pct: number | null;
  cost_inr: number | null;
  value_inr: number | null;
  pnl_inr: number | null;
  pnl_inr_pct: number | null;
  fx_gain_inr: number | null;
  advice: ExitAdvice | null;
}

export interface HoldingInput {
  symbol: string;
  quantity: number;
  avg_cost: number;
  buy_date: string | null;
  buy_fx_rate: number | null;
  notes: string | null;
}

export interface SocialPoint {
  id: string;
  label: number;
  x: number;
  y: number;
  probability: number;
  title: string;
  summary: string;
  url: string;
  publisher: string;
  source_api: string;
  platform: string;
  kind: string;
  published_at: string;
  sentiment: number | null;
  sentiment_method: string | null;
  tickers: string[];
  ticker_names: Record<string, string>;
  sectors: string[];
}

export interface SocialCluster {
  label: number;
  stable_id: string;
  size: number;
  headline: string;
  summary: string;
  summary_method: "llm" | "keywords";
  keywords: string[];
  sentiment: number | null;
  tickers: Record<string, number>;
  ticker_names: Record<string, string>;
  sectors: Record<string, number>;
  sources: Record<string, number>;
  platforms: Record<string, number>;
  cx: number;
  cy: number;
  first_published: string;
  last_published: string;
  top_article_ids: string[];
}

export interface SocialRun {
  id: number;
  created_at: string;
  embed_model: string;
  params: Record<string, string | number>;
  n_articles: number;
  n_clusters: number;
  n_noise: number;
  new_embeddings: number;
  new_summaries: number;
  seconds: number;
}

export interface SocialMap {
  run: SocialRun | null;
  clusters: SocialCluster[];
  points: SocialPoint[];
}

export interface SocialStatus {
  job: { running: boolean; stage: string; error: string | null; last_finished: string | null };
  embedder: { model: string; device: string };
  counts: { articles: number; embeddings: number; runs: number; cached_summaries: number };
  last_run: SocialRun | null;
  platforms: string[];
}

export interface StrategyPeriod {
  entry: string;
  exit: string;
  rec_date: string;
  source: string;
  holdings: string[];
  return: number;
  benchmark_return: number;
  turnover: number;
  positions: { symbol: string; entry: number; exit: number; return: number }[];
}

export interface StrategyResult {
  size: number;
  periods: number;
  start: string;
  end: string;
  days: number;
  usd: { total: number; annualised: number | null; max_drawdown: number };
  benchmark_usd: { total: number; annualised: number | null; max_drawdown: number };
  inr: { total: number; annualised: number | null };
  benchmark_inr: { total: number; annualised: number | null };
  excess_usd: number;
  win_rate: number;
  beat_benchmark_rate: number;
  avg_period_return: number;
  trades: number;
  fx_move: number;
  fx_cost: number;
  backfilled_periods: number;
  curve: { date: string; strategy: number; benchmark: number; strategy_inr: number; benchmark_inr: number }[];
  period_log: StrategyPeriod[];
}

export interface StrategyResponse {
  assumptions: Record<string, string | number | null>;
  results: StrategyResult[];
  names: Record<string, string | null>;
  recommendation_days: number;
  backfilled_days: number;
  note?: string;
}

export interface StrategyParams {
  sizes: string;
  rebalance_every: number;
  selection: "ranked" | "buyable";
  fx_markup_pct: number;
  trade_cost_pct: number;
  fx_mode: "actual" | "assumed";
  assumed_fx_annual_pct: number;
  days: number;
}

const STORAGE_KEY = "apiBase";
const DEFAULT_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export function getApiBase(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) || DEFAULT_BASE;
  } catch {
    return DEFAULT_BASE;
  }
}

export function setApiBase(url: string): void {
  try {
    if (url.trim()) localStorage.setItem(STORAGE_KEY, url.trim().replace(/\/$/, ""));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable - the default is used */
  }
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

const jsonBody = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${getApiBase()}${path}`, init);
  } catch {
    throw new ApiError(`Cannot reach the backend at ${getApiBase()}. Is it running? (docker compose up)`, 0);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = Array.isArray(body.detail) ? body.detail.map((d: { msg: string }) => d.msg).join("; ") : (body.detail ?? detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return null as T;
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/api/health"),
  latest: () => request<Run>("/api/recommendations/latest"),
  byDate: (d: string) => request<Run>(`/api/recommendations/${d}`),
  runs: () => request<RunSummary[]>("/api/runs"),
  stock: (s: string) => request<StockDetail>(`/api/stocks/${encodeURIComponent(s)}`),
  quotes: () => request<{ fetched_at: string; quotes: Record<string, Quote> }>("/api/quotes"),
  performance: (days: number) => request<Performance>(`/api/performance?days=${days}`),
  methodology: () => request<Methodology>("/api/methodology"),
  runNow: () => request<{ accepted: boolean }>("/api/runs", { method: "POST" }),
  fx: () => request<Fx>("/api/fx"),
  briefs: () => request<BriefSummary[]>("/api/briefs"),
  latestBrief: () => request<Brief>("/api/briefs/latest"),
  brief: (d: string) => request<Brief>(`/api/briefs/${d}`),
  runBrief: () => request<{ accepted: boolean }>("/api/briefs", { method: "POST" }),
  holdings: () => request<{ fx_rate: number | null; holdings: HoldingRow[]; totals: Record<string, number> }>("/api/holdings"),
  addHolding: (h: HoldingInput) => request<{ id: number }>("/api/holdings", jsonBody("POST", h)),
  deleteHolding: (id: number) => request<null>(`/api/holdings/${id}`, { method: "DELETE" }),
  universe: () => request<{ symbol: string; name: string | null; sector: string | null }[]>("/api/universe"),
  socialMap: () => request<SocialMap>("/api/social/map"),
  socialStatus: () => request<SocialStatus>("/api/social/status"),
  socialRun: () => request<{ accepted: boolean }>("/api/social/run", { method: "POST" }),
  newsSweep: () => request<{ accepted: boolean }>("/api/news/sweep", { method: "POST" }),
  strategy: (p: StrategyParams) =>
    request<StrategyResponse>(`/api/strategy?${new URLSearchParams(Object.entries(p).map(([k, v]) => [k, String(v)]))}`),
  backfill: (days: number) => request<{ accepted: boolean }>(`/api/runs/backfill?days=${days}`, { method: "POST" }),
};
