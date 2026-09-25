import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { api, type SectorRow } from "../api";
import { CitedText, EvidenceList, SentimentBadge, StanceChip } from "../components/news";
import { SectorStrength } from "../components/charts";
import { ErrorBox, Loading } from "../components/ui";
import { longDate, pct } from "../format";
import { useAsync } from "../hooks";
import { useNames } from "../names";
import { Formula, HowCalculated } from "../components/how";

const QUADRANT_NOTE: Record<SectorRow["quadrant"], string> = {
  Leading: "beating the S&P 500 and still accelerating",
  Weakening: "beating the S&P 500 but losing steam",
  Improving: "lagging the S&P 500 but turning up",
  Lagging: "lagging the S&P 500 and still fading",
  Unknown: "not enough data",
};

function Signed({ v }: { v: number | null }) {
  return <span className={`num ${v == null ? "muted" : v >= 0 ? "up" : "down"}`}>{pct(v, 1, true)}</span>;
}

export function Sectors() {
  const b = useAsync(api.latestBrief, []);
  const names = useNames();
  const [open, setOpen] = useState<string | null>(null);

  if (b.loading && !b.data) return <Loading />;
  if (b.error) return <ErrorBox message={b.error} onRetry={b.reload} />;
  const brief = b.data;
  if (!brief) return null;
  const m = brief.market;
  const sectors = [...m.sectors].sort((a, z) => a.rank - z.rank);
  const focus = sectors.filter((s) => s.stance === "Overweight");

  return (
    <>
      <section className="card">
        <div className="card-head">
          <div>
            <h2>Sector reasoning · {longDate(brief.brief_date)}</h2>
            <div className="muted small">Where to put new money today, and why. Sector ETFs vs the S&P 500 (SPY), plus our stock scores and today's news.</div>
          </div>
        </div>
        <p className="headline">
          <CitedText text={m.headline} evidence={m.evidence} />
        </p>
        <p>
          <CitedText text={m.market_narrative} evidence={m.evidence} />
        </p>
        {focus.length > 0 && (
          <>
            <h4>Focus for new money</h4>
            <div className="focus-grid">
              {focus.map((s) => (
                <div className="tile" key={s.sector}>
                  <div className="tile-label">
                    #{s.rank} · {s.etf}
                  </div>
                  <div className="tile-value focus-name">{s.sector}</div>
                  <div className="small">
                    <CitedText text={s.rationale} evidence={s.evidence} />
                  </div>
                  {s.top_symbols.length > 0 && (
                    <div className="small">
                      Top-rated:{" "}
                      {s.top_symbols.map((t, i) => (
                        <Fragment key={t}>
                          {i > 0 && ", "}
                          <Link to={`/stock/${t}`} title={names[t]}>
                            {t}
                          </Link>
                          {names[t] && <span className="muted"> ({names[t]})</span>}
                        </Fragment>
                      ))}
                    </div>
                  )}
                  <EvidenceList items={s.evidence} />
                </div>
              ))}
            </div>
          </>
        )}
        <EvidenceList items={m.evidence} />
      </section>

      <section className="card">
        <div className="card-head">
          <h3>Relative strength vs the S&P 500, last 3 months</h3>
        </div>
        <p className="muted small">Positive = the sector ETF beat SPY. This is the main evidence behind each stance.</p>
        <HowCalculated>
          <ul className="small how-list">
            <li>
              <Formula>RS = sector ETF return − SPY return</Formula> over 1 month (21 sessions) and 3 months (63).
            </li>
            <li>Rotation: Leading = RS3m ≥ 0 and RS1m ≥ 0 · Weakening = RS3m ≥ 0, RS1m &lt; 0 · Improving = RS3m &lt; 0, RS1m ≥ 0 · Lagging = both &lt; 0.</li>
            <li>
              Rank: <Formula>100 × (0.35·pct(RS3m) + 0.25·pct(RS1m) + 0.2·avg model score/100 + 0.2·share above 50-day)</Formula>.
            </li>
            <li>Stance comes from the AI reading the table and news, but a stance that contradicts the rotation (e.g. Underweight a Leading sector) is replaced by the data-driven one.</li>
          </ul>
        </HowCalculated>
        <SectorStrength rows={sectors} />
      </section>

      <section className="card">
        <div className="card-head">
          <h3>All sectors</h3>
        </div>
        <p className="muted small">
          <strong>Rotation</strong>: Leading = strong and strengthening · Weakening = strong but fading · Improving = weak but recovering · Lagging = weak and
          fading. <strong>Breadth</strong> = share of the sector's stocks we track above their 50-day average. Click a row for the reasoning.
        </p>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th className="num">#</th>
                <th>Sector</th>
                <th>Stance</th>
                <th>Rotation</th>
                <th className="num">1 wk</th>
                <th className="num">1 mo</th>
                <th className="num">3 mo</th>
                <th className="num">vs S&P 3 mo</th>
                <th className="num hide-sm">Breadth</th>
                <th className="num hide-sm">Buys</th>
                <th className="hide-md">News</th>
              </tr>
            </thead>
            <tbody>
              {sectors.map((s) => (
                <Fragment key={s.sector}>
                  <tr className={`row ${open === s.sector ? "expanded" : ""}`} onClick={() => setOpen(open === s.sector ? null : s.sector)} tabIndex={0}>
                    <td className="num muted">{s.rank}</td>
                    <td>
                      <strong>{s.sector}</strong> <span className="muted small">{s.etf}</span>
                    </td>
                    <td>
                      <StanceChip stance={s.stance} />
                    </td>
                    <td className="small" title={QUADRANT_NOTE[s.quadrant]}>
                      {s.quadrant}
                    </td>
                    <td className="num">
                      <Signed v={s.ret_1w} />
                    </td>
                    <td className="num">
                      <Signed v={s.ret_1m} />
                    </td>
                    <td className="num">
                      <Signed v={s.ret_3m} />
                    </td>
                    <td className="num">
                      <Signed v={s.rs_3m} />
                    </td>
                    <td className="num hide-sm">{pct(s.breadth_50, 0)}</td>
                    <td className="num hide-sm">
                      {s.buy_count}/{s.stock_count}
                    </td>
                    <td className="hide-md">
                      <SentimentBadge value={s.news_sentiment} />
                    </td>
                  </tr>
                  {open === s.sector && (
                    <tr className="detail-row">
                      <td colSpan={11}>
                        <p>
                          <strong>{s.sector}</strong> is {QUADRANT_NOTE[s.quadrant]}. <CitedText text={s.rationale} evidence={s.evidence} />
                        </p>
                        <EvidenceList items={s.evidence} />
                        {s.top_symbols.length > 0 && (
                          <p className="small">
                            Highest-rated stocks here:{" "}
                            {s.top_symbols.map((t, i) => (
                              <Fragment key={t}>
                                {i > 0 && ", "}
                                <Link to={`/stock/${t}`} title={names[t]}>
                            {t}
                          </Link>
                          {names[t] && <span className="muted"> ({names[t]})</span>}
                              </Fragment>
                            ))}
                          </p>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
