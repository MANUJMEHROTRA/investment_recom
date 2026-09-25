import { useMemo, useRef, useState } from "react";
import { api, type SocialCluster, type SocialPoint } from "../api";
import { Formula, HowCalculated } from "../components/how";
import { SentimentBadge } from "../components/news";
import { ErrorBox, Loading, StatTile } from "../components/ui";
import { useAsync } from "../hooks";
import { StockName, useNames } from "../names";

const PLATFORMS = ["News", "Twitter / X", "LinkedIn", "Reddit"];
const SOURCE_LABEL: Record<string, string> = { yahoo: "Yahoo Finance", finnhub: "Finnhub", sec: "SEC EDGAR" };
const DAYS = [1, 3, 7, 14];
type Tone = "all" | "positive" | "neutral" | "negative";

const toneOf = (s: number | null) => (s == null ? "neutral" : s >= 0.05 ? "positive" : s <= -0.05 ? "negative" : "neutral");
/** Diverging 5-step scale: red (negative) - grey midpoint - blue (positive). */
const sentColor = (s: number | null) =>
  s == null ? "var(--div-0)" : s <= -0.3 ? "var(--div-n2)" : s <= -0.05 ? "var(--div-n1)" : s < 0.05 ? "var(--div-0)" : s < 0.3 ? "var(--div-p1)" : "var(--div-p2)";
const ago = (iso: string) => {
  const h = (Date.now() - new Date(iso).getTime()) / 3.6e6;
  return h < 48 ? `${Math.max(1, Math.round(h))}h ago` : `${Math.round(h / 24)}d ago`;
};

interface Filters {
  ticker: string;
  sector: string;
  sources: Set<string>;
  platform: string;
  tone: Tone;
  days: number;
  text: string;
  hideNoise: boolean;
  filings: boolean;
}

function matches(p: SocialPoint, f: Filters): boolean {
  if (f.ticker && !p.tickers.includes(f.ticker)) return false;
  if (f.sector && !p.sectors.includes(f.sector)) return false;
  if (f.sources.size && !f.sources.has(p.source_api)) return false;
  if (f.platform && p.platform !== f.platform) return false;
  if (f.tone !== "all" && toneOf(p.sentiment) !== f.tone) return false;
  if (Date.now() - new Date(p.published_at).getTime() > f.days * 864e5) return false;
  if (f.hideNoise && p.label < 0) return false;
  if (!f.filings && p.kind !== "news") return false; // SEC filings cluster by template wording, not by story
  if (f.text && !`${p.title} ${p.summary}`.toLowerCase().includes(f.text.toLowerCase())) return false;
  return true;
}

function ClusterMap({
  points,
  visible,
  clusters,
  selected,
  onSelect,
}: {
  points: SocialPoint[];
  visible: Set<string>;
  clusters: SocialCluster[];
  selected: number | null;
  onSelect: (label: number | null, article?: SocialPoint) => void;
}) {
  const [hover, setHover] = useState<{ p: SocialPoint; x: number; y: number } | null>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const W = 1000;
  const H = 640;
  const pad = 24;
  // Fit the view to the visible points using robust (2nd-98th percentile) bounds, so a few
  // outliers don't squash the map; filtering therefore also zooms in. Outliers are clamped to the edge.
  const shown = points.filter((p) => visible.has(p.id));
  const q = (vals: number[], f: number) => {
    const v = [...vals].sort((a, b) => a - b);
    return v.length ? v[Math.min(v.length - 1, Math.max(0, Math.round(f * (v.length - 1))))] : 0;
  };
  const xs = (shown.length > 4 ? shown : points).map((p) => p.x);
  const ys = (shown.length > 4 ? shown : points).map((p) => p.y);
  let [x0, x1, y0, y1] = [q(xs, 0.02), q(xs, 0.98), q(ys, 0.02), q(ys, 0.98)];
  const padX = Math.max((x1 - x0) * 0.06, 0.01);
  const padY = Math.max((y1 - y0) * 0.06, 0.01);
  [x0, x1, y0, y1] = [x0 - padX, x1 + padX, y0 - padY, y1 + padY];
  const clamp = (v: number) => Math.max(0, Math.min(1, v));
  const sx = (x: number) => pad + clamp((x - x0) / (x1 - x0)) * (W - 2 * pad);
  const sy = (y: number) => pad + (1 - clamp((y - y0) / (y1 - y0))) * (H - 2 * pad);
  const lx = (x: number) => Math.max(110, Math.min(W - 110, x)); // keep centred labels inside the frame
  const byLabel = Object.fromEntries(clusters.map((c) => [c.label, c]));
  // Direct labels only for the biggest visible clusters (selective labelling).
  const visibleCounts = new Map<number, number>();
  points.forEach((p) => visible.has(p.id) && p.label >= 0 && visibleCounts.set(p.label, (visibleCounts.get(p.label) ?? 0) + 1));
  const labelled = [...visibleCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([l]) => l);
  if (selected != null && !labelled.includes(selected)) labelled.push(selected);

  const ordered = [...points].sort((a, b) => Number(a.label === selected) - Number(b.label === selected)); // selected on top

  return (
    <div className="map-wrap" ref={wrap} onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} className="map" role="img" aria-label="2D map of news articles; nearby dots are similar stories">
        <rect x={0} y={0} width={W} height={H} fill="var(--surface)" onClick={() => onSelect(null)} />
        {ordered.map((p) => {
          const on = visible.has(p.id);
          const dim = !on || (selected != null && p.label !== selected);
          const noise = p.label < 0;
          return (
            <circle
              key={p.id}
              cx={sx(p.x)}
              cy={sy(p.y)}
              r={noise ? 3.5 : 5}
              fill={noise ? "transparent" : sentColor(p.sentiment)}
              stroke={noise ? "var(--text-muted)" : "var(--surface)"}
              strokeWidth={noise ? 1 : 1.5}
              opacity={!on ? 0.05 : dim ? 0.15 : 0.95}
              style={{ cursor: on ? "pointer" : "default" }}
              onMouseEnter={(e) => {
                if (!on || !wrap.current) return;
                const box = wrap.current.getBoundingClientRect();
                setHover({ p, x: e.clientX - box.left, y: e.clientY - box.top });
              }}
              onMouseLeave={() => setHover(null)}
              onClick={(e) => {
                e.stopPropagation();
                if (on) onSelect(p.label >= 0 ? p.label : null, p);
              }}
            />
          );
        })}
        {labelled.map((l) => {
          const c = byLabel[l];
          if (!c) return null;
          const text = c.headline.split(" ").slice(0, 5).join(" ") + (c.headline.split(" ").length > 5 ? "…" : "");
          return (
            <g key={l} onClick={() => onSelect(l)} style={{ cursor: "pointer" }}>
              <text x={lx(sx(c.cx))} y={Math.max(16, sy(c.cy) - 10)} textAnchor="middle" className="map-label halo">
                {text}
              </text>
              <text x={lx(sx(c.cx))} y={Math.max(16, sy(c.cy) - 10)} textAnchor="middle" className={`map-label ${l === selected ? "sel" : ""}`}>
                {text}
              </text>
            </g>
          );
        })}
      </svg>
      {hover && (
        <div className="tip map-tip" style={{ left: Math.min(hover.x + 14, (wrap.current?.clientWidth ?? 600) - 300), top: hover.y + 14 }}>
          <div className="tip-title">{hover.p.title}</div>
          <div className="small muted">
            {hover.p.publisher} · {ago(hover.p.published_at)} · {hover.p.tickers.slice(0, 4).join(", ") || "market"}
          </div>
          <div className="small">
            Sentiment {hover.p.sentiment == null ? "—" : hover.p.sentiment.toFixed(2)} ·{" "}
            {hover.p.label >= 0 ? `cluster: ${byLabel[hover.p.label]?.headline ?? ""}` : "not in a cluster"}
          </div>
        </div>
      )}
      <div className="legend map-legend">
        <span>Sentiment:</span>
        {[
          ["var(--div-n2)", "≤ −0.3"],
          ["var(--div-n1)", "negative"],
          ["var(--div-0)", "neutral"],
          ["var(--div-p1)", "positive"],
          ["var(--div-p2)", "≥ +0.3"],
        ].map(([c, l]) => (
          <span key={l} className="legend-item">
            <span className="dot" style={{ background: c }} /> {l}
          </span>
        ))}
        <span className="legend-item">
          <span className="dot hollow" /> not in a cluster
        </span>
      </div>
    </div>
  );
}

function ClusterDetail({ c, members, onClose }: { c: SocialCluster; members: SocialPoint[]; onClose: () => void }) {
  const order = new Map(c.top_article_ids.map((id, i) => [id, i]));
  const sorted = [...members].sort((a, b) => (order.get(a.id) ?? 99) - (order.get(b.id) ?? 99) || +new Date(b.published_at) - +new Date(a.published_at));
  return (
    <div className="cluster-detail">
      <button className="linklike small" onClick={onClose}>
        ← All clusters
      </button>
      <h3 className="cluster-headline">{c.headline}</h3>
      <div className="advice-head small">
        <SentimentBadge value={c.sentiment} />
        <span>{c.size} articles</span>
        <span className="muted">
          {ago(c.last_published)} · {c.summary_method === "llm" ? "AI summary" : "keyword summary"}
        </span>
      </div>
      <p>{c.summary}</p>
      {c.keywords.length > 0 && (
        <div className="chips-row">
          {c.keywords.map((k) => (
            <span className="tag" key={k}>
              {k}
            </span>
          ))}
        </div>
      )}
      {Object.keys(c.tickers).length > 0 && (
        <>
          <h4>Stocks talked about</h4>
          <ul className="ticker-list">
            {Object.entries(c.tickers)
              .slice(0, 8)
              .map(([t, n]) => (
                <li key={t}>
                  <StockName symbol={t} name={c.ticker_names[t]} inline /> <span className="muted small">× {n}</span>
                </li>
              ))}
          </ul>
        </>
      )}
      <p className="small muted">
        Fields: {Object.keys(c.sectors).join(", ") || "—"} · Sources:{" "}
        {Object.entries(c.sources)
          .map(([s, n]) => `${SOURCE_LABEL[s] ?? s} ${n}`)
          .join(", ")}
      </p>
      <h4>Articles (most representative first)</h4>
      <ArticleRows items={sorted} />
    </div>
  );
}

function ArticleRows({ items }: { items: SocialPoint[] }) {
  return (
    <ul className="articles">
      {items.map((a) => (
        <li key={a.id}>
          <a href={a.url} target="_blank" rel="noopener noreferrer" className="article-title">
            {a.title} ↗
          </a>
          <div className="article-meta small muted">
            <span className="tag">{a.platform}</span>
            <span>{a.publisher}</span>
            <span>· {SOURCE_LABEL[a.source_api] ?? a.source_api}</span>
            <span>· {ago(a.published_at)}</span>
            {a.sentiment != null && (
              <span className={a.sentiment >= 0.05 ? "up" : a.sentiment <= -0.05 ? "down" : ""}>
                · {a.sentiment >= 0 ? "+" : ""}
                {a.sentiment.toFixed(2)}
                {a.sentiment_method === "llm" ? " (AI)" : ""}
              </span>
            )}
            {a.tickers.length > 0 && <span>· {a.tickers.slice(0, 5).join(", ")}</span>}
          </div>
        </li>
      ))}
    </ul>
  );
}

export function Social() {
  const map = useAsync(api.socialMap, []);
  const status = useAsync(api.socialStatus, [], 10_000);
  const names = useNames();
  const [f, setF] = useState<Filters>({ ticker: "", sector: "", sources: new Set(), platform: "", tone: "all", days: 14, text: "", hideNoise: false, filings: false });
  const [selected, setSelected] = useState<number | null>(null);
  const [article, setArticle] = useState<SocialPoint | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const points = map.data?.points ?? [];
  const clusters = map.data?.clusters ?? [];
  const visible = useMemo(() => new Set(points.filter((p) => matches(p, f)).map((p) => p.id)), [points, f]);
  const facets = useMemo(() => {
    const t = new Map<string, number>();
    const s = new Map<string, number>();
    const src = new Map<string, number>();
    points.forEach((p) => {
      p.tickers.forEach((x) => t.set(x, (t.get(x) ?? 0) + 1));
      p.sectors.forEach((x) => s.set(x, (s.get(x) ?? 0) + 1));
      src.set(p.source_api, (src.get(p.source_api) ?? 0) + 1);
    });
    const sort = (m: Map<string, number>) => [...m.entries()].sort((a, b) => b[1] - a[1]);
    return { tickers: sort(t), sectors: sort(s), sources: sort(src) };
  }, [points]);
  const visibleClusters = useMemo(() => {
    const count = new Map<number, number>();
    points.forEach((p) => visible.has(p.id) && p.label >= 0 && count.set(p.label, (count.get(p.label) ?? 0) + 1));
    return clusters.filter((c) => count.has(c.label)).map((c) => ({ c, n: count.get(c.label) as number }));
  }, [clusters, points, visible]);

  if (map.loading && !map.data) return <Loading label="Loading the news map…" />;
  if (map.error) return <ErrorBox message={map.error} onRetry={map.reload} />;
  const run = map.data?.run;
  const st = status.data;
  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => (setF({ ...f, [k]: v }), setSelected(null));
  const sel = selected != null ? clusters.find((c) => c.label === selected) : undefined;

  return (
    <>
      <section className="card">
        <div className="card-head">
          <div>
            <h2>Social listening</h2>
            <div className="muted small">
              Every collected article as a dot; nearby dots tell the same story. Clusters are found by a density algorithm, and each gets an AI headline.
            </div>
          </div>
          <div className="button-row">
            <button className="btn small ghost" onClick={() => api.newsSweep().then(() => setMsg("Collecting news for every tracked stock, then re-clustering — a few minutes.")).catch((e: Error) => setMsg(e.message))}>
              Collect news now
            </button>
            <button className="btn small" onClick={() => api.socialRun().then(() => setMsg("Re-clustering new articles…")).catch((e: Error) => setMsg(e.message))}>
              Re-cluster
            </button>
          </div>
        </div>
        {msg && <p className="small muted">{msg}</p>}
        <div className="tiles">
          <StatTile label="Articles on the map" value={run?.n_articles ?? 0} sub={`${visible.size} match your filters`} />
          <StatTile label="Story clusters" value={run?.n_clusters ?? 0} sub={`${run?.n_noise ?? 0} articles not in any story`} />
          <StatTile label="Embeddings saved" value={st?.counts.embeddings ?? "—"} sub={st ? `${st.embedder.model} · ${st.embedder.device}` : ""} />
          <StatTile
            label="Last run"
            value={run ? new Date(run.created_at).toLocaleTimeString() : "—"}
            sub={st?.job.running ? `running: ${st.job.stage}` : run ? `${run.new_embeddings} new embeddings, ${run.new_summaries} new summaries, ${run.seconds}s` : ""}
          />
        </div>
        <HowCalculated title="How the clustering works">
          <ol className="steps small">
            <li>
              <strong>Collect</strong>: after each morning brief the agent sweeps Yahoo Finance, SEC EDGAR and Finnhub for every tracked stock and sector. Only
              articles new since the last run are ingested (a cursor on the news feed); each is stored once in the separate social database.
            </li>
            <li>
              <strong>Embed</strong>: title + snippet → a 768-number vector with <code>{st?.embedder.model ?? "nomic-embed-text"}</code> on the Mac GPU. Vectors
              are saved (pgvector) and never recomputed.
            </li>
            <li>
              <strong>Reduce</strong>: UMAP (cosine) to 5 dimensions for clustering, and separately to 2 dimensions for this map.
            </li>
            <li>
              <strong>Cluster</strong>: HDBSCAN (min cluster size {String(run?.params.min_cluster_size ?? 3)}) - dense groups become stories, the rest stay
              unclustered. Clusters whose centroids have <Formula>cos ≥ {String(run?.params.merge_similarity ?? 0.92)}</Formula> are merged so one story = one
              cluster.
            </li>
            <li>
              <strong>Summarise</strong>: the LLM writes a headline and summary from the member headlines - only for clusters whose members changed (cached by
              member hash). Cluster sentiment = mean article sentiment; keywords = class-based TF-IDF.
            </li>
          </ol>
          <p className="small">Window: last {String(run?.params.window_days ?? 14)} days · Positions on the map show similarity, not absolute meaning.</p>
        </HowCalculated>
      </section>

      <section className="card">
        <div className="filters">
          <select value={f.ticker} onChange={(e) => set("ticker", e.target.value)} aria-label="Stock">
            <option value="">All stocks</option>
            {facets.tickers.map(([t, n]) => (
              <option key={t} value={t}>
                {t} — {names[t] ?? ""} ({n})
              </option>
            ))}
          </select>
          <select value={f.sector} onChange={(e) => set("sector", e.target.value)} aria-label="Field / sector">
            <option value="">All fields</option>
            {facets.sectors.map(([s, n]) => (
              <option key={s} value={s}>
                {s} ({n})
              </option>
            ))}
          </select>
          <div className="seg" role="group" aria-label="Source">
            {facets.sources.map(([s, n]) => {
              const on = f.sources.has(s);
              return (
                <button
                  key={s}
                  className={on ? "active" : ""}
                  aria-pressed={on}
                  onClick={() => {
                    const next = new Set(f.sources);
                    if (on) next.delete(s);
                    else next.add(s);
                    set("sources", next);
                  }}
                >
                  {SOURCE_LABEL[s] ?? s} <span className="muted">{n}</span>
                </button>
              );
            })}
          </div>
          <select value={f.platform} onChange={(e) => set("platform", e.target.value)} aria-label="Platform">
            <option value="">All platforms</option>
            {PLATFORMS.map((p) => (
              <option key={p} value={p} disabled={p !== "News"}>
                {p}
                {p !== "News" ? " (coming later)" : ""}
              </option>
            ))}
          </select>
          <select value={f.tone} onChange={(e) => set("tone", e.target.value as Tone)} aria-label="Sentiment">
            <option value="all">Any sentiment</option>
            <option value="positive">Positive</option>
            <option value="neutral">Neutral</option>
            <option value="negative">Negative</option>
          </select>
          <div className="seg" role="group" aria-label="Published within">
            {DAYS.map((d) => (
              <button key={d} className={f.days === d ? "active" : ""} onClick={() => set("days", d)} aria-pressed={f.days === d}>
                {d}d
              </button>
            ))}
          </div>
          <input className="search" placeholder="Search headlines…" value={f.text} onChange={(e) => set("text", e.target.value)} aria-label="Search headlines" />
          <label className="small check" title="Form 4 insider trades and 8-K filings group by their template wording rather than by story">
            <input type="checkbox" checked={f.filings} onChange={(e) => set("filings", e.target.checked)} /> include SEC filings
          </label>
          <label className="small check">
            <input type="checkbox" checked={f.hideNoise} onChange={(e) => set("hideNoise", e.target.checked)} /> hide unclustered
          </label>
        </div>

        {!run ? (
          <div className="callout">No clustering run yet — click “Collect news now”.</div>
        ) : (
          <div className="social-grid">
            <ClusterMap
              points={points}
              visible={visible}
              clusters={clusters}
              selected={selected}
              onSelect={(l, a) => {
                setSelected(l);
                setArticle(a ?? null);
              }}
            />
            <aside className="cluster-panel">
              {sel ? (
                <ClusterDetail c={sel} members={points.filter((p) => p.label === sel.label && visible.has(p.id))} onClose={() => setSelected(null)} />
              ) : article ? (
                <div className="cluster-detail">
                  <button className="linklike small" onClick={() => setArticle(null)}>
                    ← All clusters
                  </button>
                  <p className="small muted">This article is not part of a multi-article story.</p>
                  <ArticleRows items={[article]} />
                </div>
              ) : (
                <>
                  <h4>{visibleClusters.length} stories match</h4>
                  <ul className="cluster-list">
                    {visibleClusters.map(({ c, n }) => (
                      <li key={c.label}>
                        <button className="cluster-item" onClick={() => setSelected(c.label)}>
                          <span className="cluster-headline">{c.headline}</span>
                          <span className="small muted">
                            {n} articles · {Object.keys(c.tickers).slice(0, 3).join(", ") || Object.keys(c.sectors)[0] || "market"} · {ago(c.last_published)}
                          </span>
                          <SentimentBadge value={c.sentiment} />
                        </button>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </aside>
          </div>
        )}
      </section>
    </>
  );
}
