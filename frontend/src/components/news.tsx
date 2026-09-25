import type { ExitAction, NewsItem, SectorRow, Verdict } from "../api";

const timeAgo = (iso: string) => {
  const h = (Date.now() - new Date(iso).getTime()) / 3.6e6;
  if (h < 1) return "just now";
  if (h < 48) return `${Math.round(h)}h ago`;
  return `${Math.round(h / 24)}d ago`;
};

export function SentimentBadge({ value, label }: { value: number | null | undefined; label?: string }) {
  if (value == null) return <span className="chip neutral">No news</span>;
  const cls = value >= 0.05 ? "good" : value <= -0.05 ? "critical" : "neutral";
  const icon = value >= 0.05 ? "▲" : value <= -0.05 ? "▼" : "●";
  return (
    <span className={`chip ${cls}`} title={`Sentiment ${value.toFixed(2)} on a −1…+1 scale`}>
      <span aria-hidden>{icon}</span> {label ?? (value >= 0.05 ? "Positive" : value <= -0.05 ? "Negative" : "Neutral")} {value >= 0 ? "+" : ""}
      {value.toFixed(2)}
    </span>
  );
}

const VERDICT: Record<Verdict, [string, string]> = {
  "Strong pick": ["good", "★"],
  Pick: ["good-soft", "▲"],
  "Wait - news risk": ["warning", "⏸"],
  Watch: ["neutral", "◌"],
};

export function VerdictChip({ verdict }: { verdict: Verdict }) {
  const [cls, icon] = VERDICT[verdict];
  return (
    <span className={`chip ${cls}`}>
      <span aria-hidden>{icon}</span> {verdict.replace(" - ", " — ")}
    </span>
  );
}

const ACTION: Record<ExitAction, [string, string]> = { Add: ["good", "＋"], Hold: ["neutral", "■"], Trim: ["warning", "−"], Exit: ["critical", "✕"] };

export function ActionChip({ action, prefix }: { action: ExitAction; prefix?: string }) {
  const [cls, icon] = ACTION[action];
  return (
    <span className={`chip ${cls}`}>
      <span aria-hidden>{icon}</span> {prefix}
      {action}
    </span>
  );
}

const STANCE: Record<SectorRow["stance"], [string, string]> = { Overweight: ["good", "▲"], Neutral: ["neutral", "■"], Underweight: ["critical", "▼"] };

export function StanceChip({ stance }: { stance: SectorRow["stance"] }) {
  const [cls, icon] = STANCE[stance];
  return (
    <span className={`chip ${cls}`}>
      <span aria-hidden>{icon}</span> {stance}
    </span>
  );
}

const KIND_LABEL = { news: "", filing: "SEC filing", insider: "Insider trade" } as const;

export function ArticleList({ items, empty = "No relevant articles." }: { items: NewsItem[]; empty?: string }) {
  if (!items.length) return <p className="muted small">{empty}</p>;
  return (
    <ul className="articles">
      {items.map((a) => (
        <li key={a.id + a.url}>
          <a href={a.url} target="_blank" rel="noopener noreferrer" className="article-title">
            {a.title}
          </a>
          <div className="article-meta small muted">
            {KIND_LABEL[a.kind] && <span className="tag">{KIND_LABEL[a.kind]}</span>}
            <span>{a.publisher}</span>
            <span>· {timeAgo(a.published_at)}</span>
            {a.sentiment != null && (
              <span className={a.sentiment >= 0.05 ? "up" : a.sentiment <= -0.05 ? "down" : ""}>
                · {a.sentiment >= 0.05 ? "▲" : a.sentiment <= -0.05 ? "▼" : "●"} {a.sentiment >= 0 ? "+" : ""}
                {a.sentiment.toFixed(2)}
                {a.sentiment_method === "llm" ? " (AI)" : a.sentiment_method === "vader" ? " (lexicon)" : ""}
              </span>
            )}
          </div>
          {a.takeaway && <div className="small takeaway">{a.takeaway}</div>}
        </li>
      ))}
    </ul>
  );
}

/** Renders "[2]" markers as superscript links to the matching evidence article. */
export function CitedText({ text, evidence }: { text: string; evidence: NewsItem[] }) {
  const parts = text.split(/(\[\d+\])/g);
  return (
    <>
      {parts.map((p, i) => {
        const m = p.match(/^\[(\d+)\]$/);
        const a = m ? evidence[Number(m[1]) - 1] : undefined;
        if (!m) return <span key={i}>{p}</span>;
        return a ? (
          <sup key={i}>
            <a href={a.url} target="_blank" rel="noopener noreferrer" title={`${a.publisher}: ${a.title}`}>
              [{m[1]}]
            </a>
          </sup>
        ) : null;
      })}
    </>
  );
}

export function EvidenceList({ items }: { items: NewsItem[] }) {
  if (!items.length) return null;
  return (
    <ol className="evidence">
      {items.map((a) => (
        <li key={a.id + a.url}>
          <a href={a.url} target="_blank" rel="noopener noreferrer">
            {a.title}
          </a>{" "}
          <span className="muted small">
            — {a.publisher}, {new Date(a.published_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
            {a.sentiment != null && ` · ${a.sentiment >= 0 ? "+" : ""}${a.sentiment.toFixed(2)}`}
          </span>
        </li>
      ))}
    </ol>
  );
}
