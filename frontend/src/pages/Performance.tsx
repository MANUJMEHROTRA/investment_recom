import { useState } from "react";
import { api, type HorizonStats } from "../api";
import { GroupReturns } from "../components/charts";
import { ErrorBox, Loading, RatingChip, StatTile } from "../components/ui";
import { pct, shortDate, usd } from "../format";
import { useAsync } from "../hooks";
import { StockName } from "../names";
import { Formula, HowCalculated } from "../components/how";

const HORIZON_LABEL: Record<string, string> = { "5d": "1 week", "21d": "1 month", "63d": "3 months", to_date: "Held to today" };
const WINDOWS = [30, 90, 180, 365];

export function PerformancePage() {
  const [days, setDays] = useState(90);
  const [horizon, setHorizon] = useState("21d");
  const perf = useAsync(() => api.performance(days), [days]);

  if (perf.loading && !perf.data) return <Loading label="Scoring the track record…" />;
  if (perf.error) return <ErrorBox message={perf.error} onRetry={perf.reload} />;
  const p = perf.data;
  if (!p) return null;

  const stats = (group: string) => p.summary.find((s) => s.group === group)?.[horizon] as HorizonStats | undefined;
  const all = stats("All buy picks");
  const groups = ["Strong Buy", "Buy", "Hold", "Avoid"].map((g) => ({ group: g, value: stats(g)?.avg_return ?? null, n: stats(g)?.n ?? 0 }));

  return (
    <>
      <section className="card">
        <div className="card-head">
          <h3>Track record — did the recommendations work?</h3>
          <div className="controls">
            <div className="seg" role="group" aria-label="Lookback window">
              {WINDOWS.map((w) => (
                <button key={w} className={w === days ? "active" : ""} onClick={() => setDays(w)} aria-pressed={w === days}>
                  {w}d
                </button>
              ))}
            </div>
            <div className="seg" role="group" aria-label="Holding period">
              {(p.horizons.length ? p.horizons : ["5d", "21d", "63d", "to_date"]).map((h) => (
                <button key={h} className={h === horizon ? "active" : ""} onClick={() => setHorizon(h)} aria-pressed={h === horizon}>
                  {HORIZON_LABEL[h] ?? h}
                </button>
              ))}
            </div>
          </div>
        </div>
        <p className="muted small">
          Every Buy / Strong Buy made in the last {days} days, bought at that day's close and held for <strong>{HORIZON_LABEL[horizon]}</strong>,
          compared with buying the S&P 500 (SPY) on the same day. Picks too recent to have completed the holding period are excluded.
        </p>
        <HowCalculated>
          <ul className="small how-list">
            <li>
              Entry = the pick's closing price on its recommendation day. <Formula>forward return = close N sessions later ÷ entry − 1</Formula> (N = 5, 21, 63),
              or to the latest close for "held to today".
            </li>
            <li>
              <Formula>excess = forward return − SPY's return over the same sessions</Formula>. Win rate = share of picks with return &gt; 0; beat S&P = share with
              excess &gt; 0.
            </li>
            <li>Averages are simple means across picks (each pick counts once per recommendation day). Returns are in USD, before FX and tax.</li>
            <li>For the rupee view and top-N portfolios bought at the next open, see the Backtest page.</li>
          </ul>
        </HowCalculated>
        <div className="tiles">
          <StatTile label="Picks measured" value={all?.n ?? 0} />
          <StatTile label="Average return" value={pct(all?.avg_return, 2, true)} />
          <StatTile label="Win rate" value={pct(all?.hit_rate, 0)} sub="picks with a positive return" />
          <StatTile label="Average vs S&P 500" value={pct(all?.avg_excess, 2, true)} sub={`beat SPY ${pct(all?.beat_benchmark_rate, 0)} of the time`} />
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h3>Average {HORIZON_LABEL[horizon].toLowerCase()} return by rating</h3>
        </div>
        <p className="muted small">If the model has an edge, Strong Buy should sit above Buy, above Hold, above Avoid.</p>
        <GroupReturns data={groups} />
      </section>

      <section className="card">
        <div className="card-head">
          <h3>Individual picks</h3>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Stock</th>
                <th>Rating</th>
                <th className="num">Entry</th>
                {p.horizons.map((h) => (
                  <th key={h} className="num">
                    {HORIZON_LABEL[h] ?? h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {p.rows.slice(0, 300).map((r) => (
                <tr key={`${r.run_date}-${r.symbol}`} className="row">
                  <td className="muted">{shortDate(r.run_date)}</td>
                  <td>
                    <StockName symbol={r.symbol} name={r.name} />
                  </td>
                  <td>
                    <RatingChip rating={r.rating} />
                  </td>
                  <td className="num">{usd(r.entry_price)}</td>
                  {p.horizons.map((h) => {
                    const v = r[`ret_${h}`] as number | null;
                    return (
                      <td key={h} className={`num ${v == null ? "muted" : v >= 0 ? "up" : "down"}`}>
                        {v == null ? "pending" : pct(v, 1, true)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
