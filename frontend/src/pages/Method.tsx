import { useState } from "react";
import { api } from "../api";
import { ErrorBox, Loading, RatingChip } from "../components/ui";
import { COMPONENT_LABELS, pct } from "../format";
import { useAsync } from "../hooks";

export function Method() {
  const m = useAsync(api.methodology, []);
  const [msg, setMsg] = useState<string | null>(null);

  if (m.loading && !m.data) return <Loading />;
  if (m.error) return <ErrorBox message={m.error} onRetry={m.reload} />;
  const d = m.data;
  if (!d) return null;

  const trigger = (fn: () => Promise<unknown>, ok: string) =>
    fn()
      .then(() => setMsg(ok))
      .catch((e: Error) => setMsg(e.message));

  return (
    <>
      <section className="card">
        <div className="card-head">
          <h3>How a recommendation is made</h3>
          <span className="muted small">model v{d.model_version}</span>
        </div>
        <ol className="steps">
          <li>
            <strong>Collect.</strong> {d.data_source} Runs automatically {d.schedule}.
          </li>
          <li>
            <strong>Read the market.</strong> {d.regime}
          </li>
          <li>
            <strong>Score every stock</strong> on six factors (0–100 each), mostly relative to the other {d.universe.length} names tracked:
          </li>
        </ol>
        <div className="meters">
          {Object.entries(d.weights).map(([k, w]) => (
            <div className="meter" key={k}>
              <div className="meter-label">
                <span>{COMPONENT_LABELS[k] ?? k}</span>
                <span className="muted num">{pct(w, 0)} of score</span>
              </div>
              <div className="meter-track">
                <div className="meter-fill" style={{ width: `${(w / Math.max(...Object.values(d.weights))) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
        <dl className="defs">
          {Object.entries(d.components).map(([k, text]) => (
            <div key={k}>
              <dt>
                {COMPONENT_LABELS[k] ?? k} <span className="muted">· {pct(d.weights[k], 0)}</span>
              </dt>
              <dd>{text}</dd>
            </div>
          ))}
        </dl>
        <h4>Ratings from the weighted score</h4>
        <div className="threshold-row">
          {d.rating_thresholds.map((t) => (
            <span key={t.rating}>
              <RatingChip rating={t.rating} /> <span className="muted small">≥ {t.min_score}</span>
            </span>
          ))}
        </div>
        <h4>Guard rails</h4>
        <ul>
          {d.rules.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        <div className="callout">
          This is a rules-based screening tool for personal research, not financial advice. Past price behaviour does not guarantee future
          returns — check the Track record page to see how the model has actually performed before relying on it.
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h3>Maintenance</h3>
        </div>
        <div className="button-row">
          <button className="btn" onClick={() => trigger(api.runNow, "Run started — refresh the Today page in a minute or two.")}>
            Run analysis now
          </button>
          <button className="btn ghost" onClick={() => trigger(() => api.backfill(120), "Backfill of 120 trading days started — takes a few minutes.")}>
            Backfill 120 days of history
          </button>
        </div>
        {msg && <p className="small">{msg}</p>}
        <h4>Universe ({d.universe.length})</h4>
        <p className="small muted universe">{d.universe.join(" · ")}</p>
        <p className="small muted">
          Change it with <code>UNIVERSE=</code> in <code>.env</code>. Benchmark: {d.benchmark}.
        </p>
      </section>
    </>
  );
}
