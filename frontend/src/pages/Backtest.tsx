import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type StrategyParams, type StrategyResult } from "../api";
import { Formula, HowCalculated } from "../components/how";
import { ErrorBox, Loading } from "../components/ui";
import { pct, shortDate } from "../format";
import { useAsync } from "../hooks";
import { StockName } from "../names";

const SIZE_OPTIONS = [5, 10, 20, 30];
const COLORS = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];
const REBAL = [
  [1, "Every day"],
  [5, "Weekly"],
  [21, "Monthly"],
] as const;

function Signed({ v, digits = 1 }: { v: number | null | undefined; digits?: number }) {
  return <span className={`num ${v == null ? "muted" : v >= 0 ? "up" : "down"}`}>{pct(v, digits, true)}</span>;
}

function Curve({ results, currency }: { results: StrategyResult[]; currency: "usd" | "inr" }) {
  const key = currency === "inr" ? "strategy_inr" : "strategy";
  const bkey = currency === "inr" ? "benchmark_inr" : "benchmark";
  const dates = results[0]?.curve.map((p) => p.date) ?? [];
  const data = dates.map((d, i) => {
    const row: Record<string, number | string> = { date: d, SPY: (results[0].curve[i][bkey] - 1) as number };
    results.forEach((r) => {
      const pt = r.curve.find((p) => p.date === d);
      if (pt) row[`Top ${r.size}`] = pt[key] - 1;
    });
    return row;
  });
  const series = results.map((r, i) => ({ key: `Top ${r.size}`, color: COLORS[i % COLORS.length] }));
  return (
    <>
      <div className="legend">
        {series.map((s) => (
          <span key={s.key} className="legend-item">
            <span className="legend-line" style={{ borderColor: s.color }} /> {s.key}
          </span>
        ))}
        <span className="legend-item">
          <span className="legend-line dashed" style={{ borderColor: "var(--text-muted)" }} /> S&P 500 (SPY)
        </span>
      </div>
      <div className="chart" style={{ height: 300 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="date" tickFormatter={shortDate} minTickGap={40} stroke="var(--axis)" tick={{ fill: "var(--text-muted)", fontSize: 12 }} tickLine={false} />
            <YAxis tickFormatter={(v) => pct(v, 0, true)} width={56} stroke="var(--axis)" tick={{ fill: "var(--text-muted)", fontSize: 12 }} tickLine={false} axisLine={false} />
            <Tooltip
              cursor={{ stroke: "var(--axis)" }}
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <div className="tip">
                    <div className="tip-title">{shortDate(String(label))}</div>
                    {payload.map((p) => (
                      <div className="tip-row" key={String(p.dataKey)}>
                        <span className="swatch" style={{ background: String(p.color) }} />
                        <span>{String(p.dataKey)}</span>
                        <span className="num tip-val">{pct(Number(p.value), 2, true)}</span>
                      </div>
                    ))}
                  </div>
                ) : null
              }
            />
            {series.map((s) => (
              <Line key={s.key} dataKey={s.key} stroke={s.color} strokeWidth={2} dot={false} isAnimationActive={false} />
            ))}
            <Line dataKey="SPY" stroke="var(--text-muted)" strokeDasharray="5 4" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

export function Backtest() {
  const [p, setP] = useState<StrategyParams>({
    sizes: "5,10,20,30",
    rebalance_every: 5,
    selection: "ranked",
    fx_markup_pct: 1,
    trade_cost_pct: 0,
    fx_mode: "actual",
    assumed_fx_annual_pct: 1,
    days: 365,
  });
  const [currency, setCurrency] = useState<"usd" | "inr">("inr");
  const [log, setLog] = useState<number | null>(null);
  const res = useAsync(() => api.strategy(p), [JSON.stringify(p)]);
  const sizes = p.sizes.split(",").map(Number);
  const set = <K extends keyof StrategyParams>(k: K, v: StrategyParams[K]) => setP({ ...p, [k]: v });

  const d = res.data;
  const example = d?.results.find((r) => r.size === 10) ?? d?.results[0];

  return (
    <>
      <section className="card">
        <div className="card-head">
          <div>
            <h2>Backtest: if I had bought the recommendations</h2>
            <div className="muted small">Replays every stored recommendation day. Results in dollars and, for an India-based investor, in rupees after FX costs.</div>
          </div>
          <div className="seg" role="group" aria-label="Currency">
            <button className={currency === "inr" ? "active" : ""} onClick={() => setCurrency("inr")}>
              ₹ INR
            </button>
            <button className={currency === "usd" ? "active" : ""} onClick={() => setCurrency("usd")}>
              $ USD
            </button>
          </div>
        </div>
        <div className="filters">
          <div className="seg" role="group" aria-label="Portfolio sizes">
            {SIZE_OPTIONS.map((n) => {
              const on = sizes.includes(n);
              return (
                <button
                  key={n}
                  className={on ? "active" : ""}
                  aria-pressed={on}
                  onClick={() => {
                    const next = on ? sizes.filter((x) => x !== n) : [...sizes, n];
                    if (next.length) set("sizes", next.sort((a, b) => a - b).join(","));
                  }}
                >
                  Top {n}
                </button>
              );
            })}
          </div>
          <select value={p.rebalance_every} onChange={(e) => set("rebalance_every", Number(e.target.value))} aria-label="Rebalance">
            {REBAL.map(([v, l]) => (
              <option key={v} value={v}>
                Rebalance: {l}
              </option>
            ))}
          </select>
          <select value={p.selection} onChange={(e) => set("selection", e.target.value as StrategyParams["selection"])} aria-label="Selection">
            <option value="ranked">Top N by model rank</option>
            <option value="buyable">Top N among Buy / Strong Buy only</option>
          </select>
          <label className="small inline-input">
            FX markup % each way
            <input type="number" step="0.1" min="0" value={p.fx_markup_pct} onChange={(e) => set("fx_markup_pct", Number(e.target.value))} />
          </label>
          <select value={p.fx_mode} onChange={(e) => set("fx_mode", e.target.value as StrategyParams["fx_mode"])} aria-label="Currency move">
            <option value="actual">Currency: actual USD/INR history</option>
            <option value="assumed">Currency: assume rupee weakens…</option>
          </select>
          {p.fx_mode === "assumed" && (
            <label className="small inline-input">
              % per year
              <input type="number" step="0.5" value={p.assumed_fx_annual_pct} onChange={(e) => set("assumed_fx_annual_pct", Number(e.target.value))} />
            </label>
          )}
          <label className="small inline-input">
            Brokerage % per trade
            <input type="number" step="0.05" min="0" value={p.trade_cost_pct} onChange={(e) => set("trade_cost_pct", Number(e.target.value))} />
          </label>
        </div>
      </section>

      {res.loading && !d && <Loading label="Replaying recommendations…" />}
      {res.error && <ErrorBox message={res.error} onRetry={res.reload} />}
      {d && (
        <>
          {d.backfilled_days > 0 && (
            <div className="callout small">
              {d.backfilled_days} of {d.recommendation_days} recommendation days are <strong>backfilled</strong> (reconstructed from price history without
              fundamentals or news). Treat short histories with caution — a few weeks cannot prove an edge.
            </div>
          )}
          <section className="card">
            <div className="card-head">
              <h3>Results {d.results[0] && `· ${shortDate(d.results[0].start)} → ${shortDate(d.results[0].end)} (${d.results[0].days} days)`}</h3>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Portfolio</th>
                    <th className="num">Return {currency === "inr" ? "₹" : "$"}</th>
                    <th className="num">S&P 500 {currency === "inr" ? "₹" : "$"}</th>
                    <th className="num">vs S&P ($)</th>
                    <th className="num hide-sm">Annualised</th>
                    <th className="num hide-sm">Max drawdown</th>
                    <th className="num hide-sm">Periods won</th>
                    <th className="num hide-sm">Beat S&P</th>
                    <th className="num hide-md">Trades</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {d.results.map((r) => {
                    const main = currency === "inr" ? r.inr : r.usd;
                    const bench = currency === "inr" ? r.benchmark_inr : r.benchmark_usd;
                    return (
                      <tr key={r.size}>
                        <td>
                          <strong>Top {r.size}</strong> <span className="muted small">{r.periods} periods</span>
                        </td>
                        <td className="num">
                          <Signed v={main.total} digits={2} />
                        </td>
                        <td className="num">
                          <Signed v={bench.total} digits={2} />
                        </td>
                        <td className="num">
                          <Signed v={r.excess_usd} digits={2} />
                        </td>
                        <td className="num hide-sm">{main.annualised == null ? <span className="muted" title="Only annualised with at least 1 year of history">&lt; 1 yr</span> : <Signed v={main.annualised} />}</td>
                        <td className="num hide-sm">{pct(r.usd.max_drawdown, 1)}</td>
                        <td className="num hide-sm">{pct(r.win_rate, 0)}</td>
                        <td className="num hide-sm">{pct(r.beat_benchmark_rate, 0)}</td>
                        <td className="num hide-md">{r.trades}</td>
                        <td>
                          <button className="linklike small" onClick={() => setLog(log === r.size ? null : r.size)}>
                            {log === r.size ? "hide" : "trades"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {d.note && <p className="muted">{d.note}</p>}
            {d.results.length > 0 && <Curve results={d.results} currency={currency} />}

            {example && (
              <HowCalculated>
                <ul className="small how-list">
                  <li>{String(d.assumptions.entry)}; {String(d.assumptions.exit).toLowerCase()}.</li>
                  <li>
                    {String(d.assumptions.weighting)}; {String(d.assumptions.selection).toLowerCase()}; rebalanced every {p.rebalance_every} recommendation day(s).
                  </li>
                  <li>
                    Period return = average of each holding's <Formula>exit open ÷ entry open − 1</Formula>; growth compounds:{" "}
                    <Formula>equity = Π(1 + period return − brokerage × turnover)</Formula>.
                  </li>
                  <li>
                    Rupees: <Formula>{String(d.assumptions.inr_formula)}</Formula>. You convert once at the start and once at the end.
                  </li>
                  <li>
                    Worked example, Top {example.size}: USD {pct(example.usd.total, 2, true)} × currency move {pct(example.fx_move, 2, true)} (
                    {p.fx_mode === "actual" ? "actual USD/INR" : `assumed ${p.assumed_fx_annual_pct}%/yr`}) × FX cost (1 − {p.fx_markup_pct}%)² ={" "}
                    <strong>INR {pct(example.inr.total, 2, true)}</strong>. The S&P 500 over the same days: USD {pct(example.benchmark_usd.total, 2, true)} → INR{" "}
                    {pct(example.benchmark_inr.total, 2, true)}.
                  </li>
                  <li>
                    Biases to keep in mind: today's universe (survivorship), backfilled days use price data only, and no taxes are modelled (capital gains, US
                    dividend withholding).
                  </li>
                </ul>
              </HowCalculated>
            )}
          </section>

          {log != null &&
            (() => {
              const r = d.results.find((x) => x.size === log);
              if (!r) return null;
              return (
                <section className="card">
                  <div className="card-head">
                    <h3>Top {r.size}: every period</h3>
                  </div>
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Recommended</th>
                          <th>Bought → sold</th>
                          <th className="num">Return</th>
                          <th className="num">S&P 500</th>
                          <th>Holdings (return)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[...r.period_log].reverse().map((pr) => (
                          <tr key={pr.entry}>
                            <td className="small">
                              {shortDate(pr.rec_date)} {pr.source === "backfill" && <span className="tag">backfill</span>}
                            </td>
                            <td className="small">
                              {shortDate(pr.entry)} → {shortDate(pr.exit)}
                            </td>
                            <td className="num">
                              <Signed v={pr.return} digits={2} />
                            </td>
                            <td className="num">
                              <Signed v={pr.benchmark_return} digits={2} />
                            </td>
                            <td className="small holdings-cell">
                              {pr.positions.map((pos) => (
                                <span key={pos.symbol} className="holding-chip" title={d.names[pos.symbol] ?? ""}>
                                  <StockName symbol={pos.symbol} name={d.names[pos.symbol]} inline /> <Signed v={pos.return} />
                                </span>
                              ))}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              );
            })()}
        </>
      )}
    </>
  );
}
