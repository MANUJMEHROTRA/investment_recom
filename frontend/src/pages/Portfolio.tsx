import { Fragment, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, type HoldingInput, type HoldingRow } from "../api";
import { inr, usdFmt } from "../currency";
import { ActionChip, ArticleList, CitedText, EvidenceList, SentimentBadge } from "../components/news";
import { ErrorBox, Loading, StatTile } from "../components/ui";
import { longDate, pct } from "../format";
import { useAsync } from "../hooks";

const EMPTY = { symbol: "", quantity: "", avg_cost: "", buy_date: "", buy_fx_rate: "", notes: "" };

function AddHolding({ onAdded }: { onAdded: () => void }) {
  const [f, setF] = useState(EMPTY);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: keyof typeof EMPTY) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const body: HoldingInput = {
      symbol: f.symbol.trim().toUpperCase(),
      quantity: Number(f.quantity),
      avg_cost: Number(f.avg_cost),
      buy_date: f.buy_date || null,
      buy_fx_rate: f.buy_fx_rate ? Number(f.buy_fx_rate) : null,
      notes: f.notes || null,
    };
    api
      .addHolding(body)
      .then(() => {
        setF(EMPTY);
        setErr(null);
        onAdded();
      })
      .catch((x: Error) => setErr(x.message));
  };

  return (
    <form className="holding-form" onSubmit={submit}>
      <label>
        Ticker
        <input required value={f.symbol} onChange={set("symbol")} placeholder="AAPL" maxLength={16} />
      </label>
      <label>
        Shares
        <input required type="number" step="any" min="0" value={f.quantity} onChange={set("quantity")} placeholder="2.5" />
      </label>
      <label>
        Avg cost ($/share)
        <input required type="number" step="any" min="0" value={f.avg_cost} onChange={set("avg_cost")} placeholder="180.00" />
      </label>
      <label>
        Buy date
        <input type="date" value={f.buy_date} onChange={set("buy_date")} />
      </label>
      <label>
        ₹ per $ when bought
        <input type="number" step="any" min="0" value={f.buy_fx_rate} onChange={set("buy_fx_rate")} placeholder="auto from date" />
      </label>
      <label className="wide">
        Notes
        <input value={f.notes} onChange={set("notes")} placeholder="optional" maxLength={500} />
      </label>
      <button className="btn">Add holding</button>
      {err && <p className="small down">{err}</p>}
    </form>
  );
}

function AdviceCard({ h }: { h: HoldingRow }) {
  const a = h.advice;
  const [more, setMore] = useState(false);
  if (!a) return <p className="muted small">No exit review yet — it runs with the next morning brief.</p>;
  return (
    <div className="advice">
      <div className="advice-head">
        <ActionChip action={a.action} /> <span className="small">confidence {a.confidence}</span>
        {a.quant_action && a.quant_action !== a.action && (
          <span className="small muted">
            (rules said <ActionChip action={a.quant_action} />)
          </span>
        )}
        <SentimentBadge value={a.news_sentiment} label={a.sentiment_label} />
        <span className="small muted">
          {a.method === "llm" ? "AI review" : "rules review"} · {a.brief_date && longDate(a.brief_date)}
        </span>
      </div>
      <p>
        <CitedText text={a.rationale} evidence={a.evidence} />
      </p>
      <div className="reasons">
        <div>
          <h4>Reasons to exit</h4>
          {a.reasons_to_exit.length ? (
            <ul className="cons">
              {a.reasons_to_exit.map((r) => (
                <li key={r}>
                  <CitedText text={r} evidence={a.evidence} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">None.</p>
          )}
        </div>
        <div>
          <h4>Reasons to hold</h4>
          {a.reasons_to_hold.length ? (
            <ul className="pros">
              {a.reasons_to_hold.map((r) => (
                <li key={r}>
                  <CitedText text={r} evidence={a.evidence} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">None.</p>
          )}
        </div>
      </div>
      <EvidenceList items={a.evidence} />
      <p className="small muted">
        Trailing stop {usdFmt(a.signal.trailing_stop)} · model rating {a.signal.rating ?? "—"} {a.signal.score != null && `(${a.signal.score.toFixed(0)})`}
        {a.articles.length > 0 && (
          <>
            {" "}
            ·{" "}
            <button className="linklike small" onClick={() => setMore(!more)}>
              {more ? "hide articles" : `${a.articles.length} articles read`}
            </button>
          </>
        )}
      </p>
      {more && <ArticleList items={a.articles} />}
    </div>
  );
}

export function Portfolio() {
  const data = useAsync(api.holdings, []);
  const [open, setOpen] = useState<number | null>(null);

  if (data.loading && !data.data) return <Loading />;
  if (data.error) return <ErrorBox message={data.error} onRetry={data.reload} />;
  const d = data.data;
  if (!d) return null;
  const t = d.totals;

  return (
    <>
      <section className="card">
        <div className="card-head">
          <h3>Your holdings</h3>
          <span className="muted small">Stored only in your local database. {d.fx_rate && `1 USD = ₹${d.fx_rate.toFixed(2)}`}</span>
        </div>
        {d.holdings.length > 0 && (
          <div className="tiles">
            <StatTile label="Value" value={inr(t.value_inr)} sub={usdFmt(t.value_usd, 0)} />
            <StatTile label="Gain / loss in ₹" value={<span className={t.pnl_inr >= 0 ? "up" : "down"}>{inr(t.pnl_inr)}</span>} sub={t.cost_inr ? pct(t.pnl_inr / t.cost_inr, 1, true) : undefined} />
            <StatTile label="Gain / loss in $" value={<span className={t.pnl_usd >= 0 ? "up" : "down"}>{usdFmt(t.pnl_usd, 0)}</span>} sub={t.cost_usd ? pct(t.pnl_usd / t.cost_usd, 1, true) : undefined} />
            <StatTile label="From the currency move" value={inr(t.fx_gain_inr)} sub="dollar vs rupee since you bought" />
          </div>
        )}
        <AddHolding onAdded={data.reload} />
      </section>

      {d.holdings.length === 0 ? (
        <p className="muted">Add what you own above. The next morning brief will review each position: add, hold, trim or exit, with the evidence.</p>
      ) : (
        <section className="card">
          <div className="card-head">
            <h3>Exit review</h3>
            <button className="btn small ghost" onClick={() => api.runBrief().catch(() => undefined)}>
              Re-run review now
            </button>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Stock</th>
                  <th>Advice</th>
                  <th className="num">Shares</th>
                  <th className="num">Cost</th>
                  <th className="num">Price</th>
                  <th className="num">P/L $</th>
                  <th className="num">P/L ₹</th>
                  <th className="num hide-sm">FX effect</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {d.holdings.map((h) => (
                  <Fragment key={h.id}>
                    <tr className={`row ${open === h.id ? "expanded" : ""}`} onClick={() => setOpen(open === h.id ? null : h.id)} tabIndex={0}>
                      <td>
                        <Link to={`/stock/${h.symbol}`} onClick={(e) => e.stopPropagation()}>
                          <strong>{h.symbol}</strong>
                        </Link>
                        <div className="muted small ellipsis">{h.name}</div>
                      </td>
                      <td>{h.advice ? <ActionChip action={h.advice.action} /> : <span className="muted small">pending</span>}</td>
                      <td className="num">{h.quantity}</td>
                      <td className="num">{usdFmt(h.avg_cost)}</td>
                      <td className="num">{usdFmt(h.price)}</td>
                      <td className={`num ${(h.pnl_pct ?? 0) >= 0 ? "up" : "down"}`}>{pct(h.pnl_pct, 1, true)}</td>
                      <td className={`num ${(h.pnl_inr_pct ?? 0) >= 0 ? "up" : "down"}`}>{pct(h.pnl_inr_pct, 1, true)}</td>
                      <td className="num hide-sm" title={h.buy_fx_is_estimate ? "Buy-date rate looked up from history" : "Your entered rate"}>
                        {inr(h.fx_gain_inr)}
                      </td>
                      <td>
                        <button
                          className="linklike small"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (confirm(`Remove ${h.symbol} from your holdings?`)) api.deleteHolding(h.id).then(data.reload);
                          }}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                    {open === h.id && (
                      <tr className="detail-row">
                        <td colSpan={9}>
                          <AdviceCard h={h} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
