import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import type { Quote, Recommendation } from "../api";
import { useCurrency } from "../currency";
import { pct } from "../format";
import { ComponentMeters, Delta, RatingChip, ReasonList, ScoreBar } from "./ui";

// Almost every pick is in an uptrend, so surface the first reason that says something more specific.
const keyReason = (r: Recommendation) => r.reasons.find((x) => !/uptrend|200-day average/.test(x)) ?? r.reasons[0];

interface Props {
  recs: Recommendation[];
  quotes?: Record<string, Quote>;
}

export function RecTable({ recs, quotes }: Props) {
  const [open, setOpen] = useState<string | null>(null);
  const { money } = useCurrency();
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th className="num">#</th>
            <th>Stock</th>
            <th>Rating</th>
            <th>Score</th>
            <th className="num">{quotes ? "Live price" : "Price"}</th>
            {quotes && <th className="num">Today</th>}
            <th className="num hide-sm">Weight</th>
            <th className="num hide-sm">Stop-loss</th>
            <th className="hide-md">Top reason</th>
          </tr>
        </thead>
        <tbody>
          {recs.map((r) => {
            const q = quotes?.[r.symbol];
            const expanded = open === r.symbol;
            return (
              <Fragment key={r.symbol}>
                <tr
                  className={`row ${expanded ? "expanded" : ""}`}
                  onClick={() => setOpen(expanded ? null : r.symbol)}
                  aria-expanded={expanded}
                  tabIndex={0}
                  onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setOpen(expanded ? null : r.symbol))}
                >
                  <td className="num muted">{r.rank}</td>
                  <td>
                    <div className="sym">
                      <span className="caret" aria-hidden>
                        {expanded ? "▾" : "▸"}
                      </span>
                      <strong>{r.symbol}</strong>
                    </div>
                    <div className="muted small ellipsis">{r.name ?? ""}</div>
                    <div className="muted small ellipsis">{[r.cap_category && `${r.cap_category} cap`, r.sector].filter(Boolean).join(" · ")}</div>
                  </td>
                  <td>
                    <RatingChip rating={r.rating} />
                  </td>
                  <td>
                    <ScoreBar score={r.score} />
                  </td>
                  <td className="num">{money(q?.price ?? r.price)}</td>
                  {quotes && (
                    <td className="num">
                      <Delta value={q?.change_pct} />
                    </td>
                  )}
                  <td className="num hide-sm">{r.target_weight ? pct(r.target_weight, 1) : <span className="muted">—</span>}</td>
                  <td className="num hide-sm">{money(r.stop_loss)}</td>
                  <td className="hide-md small reason-cell">{keyReason(r) ?? <span className="muted">—</span>}</td>
                </tr>
                {expanded && (
                  <tr className="detail-row">
                    <td colSpan={quotes ? 9 : 8}>
                      <div className="detail">
                        <ReasonList reasons={r.reasons} cautions={r.cautions} />
                        <div>
                          <h4>Score breakdown</h4>
                          <ComponentMeters components={r.components} />
                          <Link className="btn small" to={`/stock/${r.symbol}`}>
                            Open {r.symbol} charts →
                          </Link>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
