import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { ErrorBox, Loading, RegimeBadge } from "../components/ui";
import { longDate } from "../format";
import { useAsync } from "../hooks";
import { RunView } from "./Dashboard";

export function History() {
  const runs = useAsync(api.runs, []);
  if (runs.loading && !runs.data) return <Loading />;
  if (runs.error) return <ErrorBox message={runs.error} onRetry={runs.reload} />;
  if (!runs.data?.length) return <p className="muted">No runs stored yet.</p>;

  return (
    <section className="card">
      <div className="card-head">
        <h3>Every day's recommendations ({runs.data.length} days stored)</h3>
      </div>
      <p className="muted small">
        Each row is a snapshot saved in your local Postgres. <em>backfill</em> rows were reconstructed from price history (no fundamentals, no look-ahead).
      </p>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Regime</th>
              <th className="num">Buys</th>
              <th>Top picks</th>
              <th className="hide-sm">Source</th>
            </tr>
          </thead>
          <tbody>
            {runs.data.map((r) => (
              <tr key={r.run_date} className="row">
                <td>
                  <Link to={`/history/${r.run_date}`}>{longDate(r.run_date)}</Link>
                </td>
                <td>
                  <RegimeBadge regime={r.regime} />
                </td>
                <td className="num">{r.buy_count}</td>
                <td className="small">
                  {r.top_picks.length ? (
                    r.top_picks.map((t, i) => (
                      <span key={t} title={r.top_pick_names?.[t] ?? ""}>
                        {i > 0 && " · "}
                        <strong>{t}</strong> <span className="muted">{r.top_pick_names?.[t] ?? ""}</span>
                      </span>
                    ))
                  ) : (
                    <span className="muted">stay in cash</span>
                  )}
                </td>
                <td className="hide-sm muted small">{r.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function HistoryDay() {
  const { date = "" } = useParams();
  const run = useAsync(() => api.byDate(date), [date]);
  if (run.loading && !run.data) return <Loading />;
  if (run.error) return <ErrorBox message={run.error} onRetry={run.reload} />;
  if (!run.data) return null;
  return (
    <>
      <Link to="/history" className="back">
        ← All days
      </Link>
      <RunView run={run.data} />
    </>
  );
}
