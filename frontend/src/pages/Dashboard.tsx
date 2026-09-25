import { useState } from "react";
import { api, type CapCategory, type Quote, type Recommendation, type Run } from "../api";
import { RecTable } from "../components/RecTable";
import { Delta, ErrorBox, Loading, RegimeBadge, StatTile } from "../components/ui";
import { isMarketOpen, longDate, num, pct, usd } from "../format";
import { useAsync } from "../hooks";
import { Formula, HowCalculated } from "../components/how";

export function RegimePanel({ run }: { run: Run }) {
  const m = run.regime.metrics;
  return (
    <section className="card regime">
      <div className="card-head">
        <h3>
          Market regime <RegimeBadge regime={run.regime} />
        </h3>
        <span className="muted small">
          Analysis for {longDate(run.run_date)} · model v{run.model_version} · {run.source}
        </span>
      </div>
      <p className="regime-summary">{run.regime.summary}</p>
      <div className="tiles">
        <StatTile label="Suggested equity exposure" value={pct(run.regime.equity_exposure, 0)} sub="rest in cash / T-bills" />
        <StatTile label="S&P 500 (SPY) 1-month" value={pct(m.benchmark_ret_1m, 1, true)} sub={`3-month ${pct(m.benchmark_ret_3m, 1, true)}`} />
        <StatTile label="VIX (fear gauge)" value={num(m.vix, 1)} sub="<20 calm · >25 fearful" />
        <StatTile label="Breadth" value={pct(m.breadth_above_200, 0)} sub="of stocks above 200-day avg" />
      </div>
    </section>
  );
}

const CAPS: CapCategory[] = ["Mega", "Large", "Mid", "Small", "ETF"];
const RATING_FILTERS = { all: "All ratings", buy: "Buy & Strong Buy", Hold: "Hold", Avoid: "Avoid" } as const;

function Filters({
  recs,
  cap,
  setCap,
  sector,
  setSector,
  rating,
  setRating,
}: {
  recs: Recommendation[];
  cap: CapCategory | "all";
  setCap: (c: CapCategory | "all") => void;
  sector: string;
  setSector: (s: string) => void;
  rating: keyof typeof RATING_FILTERS;
  setRating: (r: keyof typeof RATING_FILTERS) => void;
}) {
  const sectors = [...new Set(recs.map((r) => r.sector).filter((s): s is string => !!s))].sort();
  const count = (c: CapCategory) => recs.filter((r) => r.cap_category === c).length;
  return (
    <div className="filters">
      <div className="seg" role="group" aria-label="Company size">
        <button className={cap === "all" ? "active" : ""} onClick={() => setCap("all")} aria-pressed={cap === "all"}>
          All sizes
        </button>
        {CAPS.map((c) => (
          <button key={c} className={cap === c ? "active" : ""} onClick={() => setCap(c)} aria-pressed={cap === c} disabled={!count(c)} title={capHelp[c]}>
            {c === "ETF" ? "ETFs" : `${c} cap`} <span className="muted">{count(c)}</span>
          </button>
        ))}
      </div>
      <select value={sector} onChange={(e) => setSector(e.target.value)} aria-label="Sector">
        <option value="">All sectors</option>
        {sectors.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
      <select value={rating} onChange={(e) => setRating(e.target.value as keyof typeof RATING_FILTERS)} aria-label="Rating">
        {Object.entries(RATING_FILTERS).map(([k, v]) => (
          <option key={k} value={k}>
            {v}
          </option>
        ))}
      </select>
    </div>
  );
}

const capHelp: Record<CapCategory, string> = {
  Mega: "Market cap above $200B",
  Large: "$10B – $200B",
  Mid: "$2B – $10B",
  Small: "$300M – $2B",
  Micro: "Below $300M",
  ETF: "Exchange-traded funds",
};

export function RunView({ run, quotes }: { run: Run; quotes?: Record<string, Quote> }) {
  const [showAll, setShowAll] = useState(false);
  const [cap, setCap] = useState<CapCategory | "all">("all");
  const [sector, setSector] = useState("");
  const [rating, setRating] = useState<keyof typeof RATING_FILTERS>("all");
  const filtering = cap !== "all" || sector !== "" || rating !== "all";
  const matches = (r: Recommendation) =>
    (cap === "all" || r.cap_category === cap) &&
    (!sector || r.sector === sector) &&
    (rating === "all" || (rating === "buy" ? r.rating === "Buy" || r.rating === "Strong Buy" : r.rating === rating));

  const picks = run.recommendations.filter((r) => r.target_weight);
  const shown = filtering
    ? run.recommendations.filter(matches)
    : showAll
      ? run.recommendations
      : picks.length
        ? picks
        : run.recommendations.slice(0, 10);
  const title = filtering
    ? `${shown.length} matching of ${run.recommendations.length}`
    : showAll
      ? `Full ranking (${run.recommendations.length} analysed)`
      : `Top picks (${picks.length})`;
  return (
    <>
      <RegimePanel run={run} />
      <section className="card">
        <div className="card-head">
          <h3>{title}</h3>
          {filtering ? (
            <button className="btn small ghost" onClick={() => (setCap("all"), setSector(""), setRating("all"))}>
              Clear filters
            </button>
          ) : (
            <button className="btn small ghost" onClick={() => setShowAll(!showAll)}>
              {showAll ? "Show top picks only" : "Show full ranking"}
            </button>
          )}
        </div>
        <Filters recs={run.recommendations} cap={cap} setCap={setCap} sector={sector} setSector={setSector} rating={rating} setRating={setRating} />
        {filtering && !shown.length && <div className="callout">Nothing matches these filters today.</div>}
        {!filtering && !picks.length && !showAll && (
          <div className="callout">No stock cleared the Buy threshold today — the model suggests staying in cash. Showing the highest-ranked names for reference.</div>
        )}
        <p className="muted small">
          Click a row for the full reasoning. <strong>Weight</strong> = suggested share of your investable money (inverse-volatility,
          scaled by the market regime). <strong>Stop-loss</strong> = 2× average true range below the close.
        </p>
        <RecTable recs={shown} quotes={quotes} />
        <HowCalculated>
          <ul className="small how-list">
            <li>
              <Formula>score = 0.25·trend + 0.25·momentum + 0.15·relative strength + 0.10·timing + 0.15·risk + 0.10·fundamentals</Formula> — each component 0–100;
              momentum, relative strength and risk are percentile ranks against the other stocks today.
            </li>
            <li>Ratings: Strong Buy ≥ 78 · Buy ≥ 65 · Hold ≥ 45 · Avoid. A confirmed downtrend caps at Hold; Risk-Off downgrades Strong Buy.</li>
            <li>
              <Formula>weight_i = (1/volatility_i) / Σ(1/volatility) × regime exposure</Formula> for the top {10} buy-rated names ·{" "}
              <Formula>stop-loss = close − 2 × ATR14</Formula>.
            </li>
            <li>Size buckets from market cap: Mega ≥ $200B, Large ≥ $10B, Mid ≥ $2B, Small ≥ $300M.</li>
          </ul>
        </HowCalculated>
        {Object.keys(run.skipped).length > 0 && (
          <details className="small muted skipped">
            <summary>{Object.keys(run.skipped).length} symbols skipped</summary>
            {Object.entries(run.skipped).map(([s, why]) => (
              <div key={s}>
                {s}: {why}
              </div>
            ))}
          </details>
        )}
      </section>
    </>
  );
}

function QuoteStrip({ quotes, fetchedAt }: { quotes: Record<string, Quote>; fetchedAt: string }) {
  const spy = quotes["SPY"];
  const vix = quotes["^VIX"];
  return (
    <div className="quote-strip">
      <span className={`live-dot ${isMarketOpen() ? "on" : ""}`} aria-hidden />
      <span className="muted small">{isMarketOpen() ? "Market open · quotes refresh every minute" : "Market closed · last close"}</span>
      {spy && (
        <span>
          S&P 500 <strong className="num">{usd(spy.price)}</strong> <Delta value={spy.change_pct} />
        </span>
      )}
      {vix && (
        <span>
          VIX <strong className="num">{num(vix.price, 2)}</strong> <Delta value={vix.change_pct} />
        </span>
      )}
      <span className="muted small">updated {new Date(fetchedAt).toLocaleTimeString()}</span>
    </div>
  );
}

export function Dashboard() {
  const run = useAsync(api.latest, []);
  const quotes = useAsync(api.quotes, [run.data?.run_date], isMarketOpen() ? 60_000 : undefined);

  if (run.loading && !run.data) return <Loading label="Loading today's recommendations…" />;
  if (run.error) return <ErrorBox message={run.error} onRetry={run.reload} />;
  if (!run.data) return null;

  return (
    <>
      {quotes.data && <QuoteStrip quotes={quotes.data.quotes} fetchedAt={quotes.data.fetched_at} />}
      <RunView run={run.data} quotes={quotes.data?.quotes} />
    </>
  );
}
