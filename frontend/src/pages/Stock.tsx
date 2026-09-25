import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { PriceAndRsi, ScoreHistory } from "../components/charts";
import { ComponentMeters, ErrorBox, Loading, RatingChip, ReasonList, StatTile } from "../components/ui";
import { compact, longDate, num, pct } from "../format";
import { useAsync } from "../hooks";
import { ArticleList } from "../components/news";
import { useCurrency } from "../currency";

export function Stock() {
  const { symbol = "" } = useParams();
  const nav = useNavigate();
  const detail = useAsync(() => api.stock(symbol), [symbol]);
  const { money } = useCurrency();

  if (detail.loading && !detail.data) return <Loading label={`Loading ${symbol}…`} />;
  if (detail.error) return <ErrorBox message={detail.error} onRetry={detail.reload} />;
  const d = detail.data;
  if (!d) return null;
  const rec = d.latest;
  const m = rec?.metrics ?? {};

  return (
    <>
      <button className="back linklike" onClick={() => nav(-1)}>
        ← Back
      </button>
      <section className="card">
        <div className="card-head">
          <div>
            <h2 className="stock-title">
              {d.symbol} {rec && <RatingChip rating={rec.rating} />}
            </h2>
            <div className="muted">
              {[d.info.name, rec?.cap_category && `${rec.cap_category} cap`, d.info.sector, d.info.industry].filter(Boolean).join(" · ")}
            </div>
          </div>
          {rec && (
            <div className="muted small">
              Rank #{rec.rank} on {rec.run_date && longDate(rec.run_date)}
            </div>
          )}
        </div>
        <div className="tiles">
          <StatTile label="Score" value={rec ? rec.score.toFixed(1) : "—"} sub="out of 100" />
          <StatTile label="Price" value={money(rec?.price)} sub={rec?.stop_loss ? `stop-loss ${money(rec.stop_loss)}` : undefined} />
          <StatTile label="12-1 month return" value={pct(m.ret_12m_ex1m as number, 1, true)} sub={`6-month ${pct(m.ret_6m as number, 1, true)}`} />
          <StatTile label="Volatility (3m, ann.)" value={pct(m.volatility_3m as number, 0)} sub={`max drawdown ${pct(m.max_drawdown_1y as number, 0)}`} />
          <StatTile label="Forward P/E" value={num(d.info.forward_pe as number, 1)} sub={`mkt cap ${compact(d.info.market_cap as number)}`} />
        </div>
      </section>

      {rec && (
        <section className="card">
          <div className="detail">
            <ReasonList reasons={rec.reasons} cautions={rec.cautions} />
            <div>
              <h4>Score breakdown</h4>
              <ComponentMeters components={rec.components} />
            </div>
          </div>
        </section>
      )}

      <PriceAndRsi ind={d.indicators} stopLoss={rec?.stop_loss} />

      <section className="card">
        <div className="card-head">
          <h3>Recent news & filings</h3>
          <span className="muted small">collected by the morning-brief agent</span>
        </div>
        <ArticleList items={d.news} empty="No articles stored yet for this stock — news is gathered for top candidates and your holdings each morning." />
      </section>

      <section className="card">
        <div className="card-head">
          <h3>Model score over time</h3>
        </div>
        <ScoreHistory history={d.history} />
      </section>
    </>
  );
}
