import type { ReactNode } from "react";
import type { Rating, Regime } from "../api";
import { COMPONENT_LABELS, pct } from "../format";

const RATING_CLASS: Record<Rating, string> = {
  "Strong Buy": "good",
  Buy: "good-soft",
  Hold: "warning",
  Avoid: "critical",
};
const RATING_ICON: Record<Rating, string> = { "Strong Buy": "▲▲", Buy: "▲", Hold: "■", Avoid: "▼" };

export function RatingChip({ rating }: { rating: Rating }) {
  return (
    <span className={`chip ${RATING_CLASS[rating]}`}>
      <span aria-hidden>{RATING_ICON[rating]}</span> {rating}
    </span>
  );
}

const REGIME_CLASS = { "Risk-On": "good", Neutral: "warning", "Risk-Off": "critical" } as const;
const REGIME_ICON = { "Risk-On": "●", Neutral: "◐", "Risk-Off": "○" } as const;

export function RegimeBadge({ regime }: { regime: Regime }) {
  return (
    <span className={`chip ${REGIME_CLASS[regime.label]}`}>
      <span aria-hidden>{REGIME_ICON[regime.label]}</span> {regime.label}
    </span>
  );
}

/** Inline 0–100 score bar with the number beside it. */
export function ScoreBar({ score }: { score: number }) {
  return (
    <span className="scorebar" title={`Score ${score.toFixed(1)} / 100`}>
      <span className="scorebar-track">
        <span className="scorebar-fill" style={{ width: `${Math.max(2, Math.min(100, score))}%` }} />
      </span>
      <span className="num">{score.toFixed(1)}</span>
    </span>
  );
}

export function ComponentMeters({ components, weights }: { components: Record<string, number>; weights?: Record<string, number> }) {
  return (
    <div className="meters">
      {Object.entries(components).map(([k, v]) => (
        <div className="meter" key={k}>
          <div className="meter-label">
            <span>{COMPONENT_LABELS[k] ?? k}</span>
            <span className="muted num">
              {v.toFixed(0)}
              {weights?.[k] != null && <> · {pct(weights[k], 0)} weight</>}
            </span>
          </div>
          <div className="meter-track">
            <div className="meter-fill" style={{ width: `${Math.max(1, v)}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function Delta({ value, digits = 2 }: { value: number | null | undefined; digits?: number }) {
  if (value == null) return <span className="muted">—</span>;
  const cls = value > 0 ? "up" : value < 0 ? "down" : "muted";
  return (
    <span className={`num ${cls}`}>
      {value > 0 ? "▲" : value < 0 ? "▼" : ""} {pct(Math.abs(value), digits)}
    </span>
  );
}

export function StatTile({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {sub && <div className="tile-sub">{sub}</div>}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="callout critical-callout" role="alert">
      <strong>Couldn't load data.</strong> {message}
      {onRetry && (
        <button className="btn small" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="loading">{label}</div>;
}

export function ReasonList({ reasons, cautions }: { reasons: string[]; cautions: string[] }) {
  return (
    <div className="reasons">
      <div>
        <h4>Why it's recommended</h4>
        {reasons.length ? (
          <ul className="pros">
            {reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">No strong positive signals.</p>
        )}
      </div>
      <div>
        <h4>Watch out for</h4>
        {cautions.length ? (
          <ul className="cons">
            {cautions.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">No red flags detected.</p>
        )}
      </div>
    </div>
  );
}
