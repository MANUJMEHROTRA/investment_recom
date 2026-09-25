import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Brief, type BriefPick, type Fx, type Verdict } from "../api";
import { inr, useCurrency, usdFmt } from "../currency";
import { ArticleList, CitedText, EvidenceList, SentimentBadge, VerdictChip } from "../components/news";
import { Loading, RatingChip, RegimeBadge, StatTile } from "../components/ui";
import { longDate, pct } from "../format";
import { useAsync } from "../hooks";
import { StockName } from "../names";
import { Formula, HowCalculated } from "../components/how";

function RunBriefButton({ label = "Run the brief now" }: { label?: string }) {
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <span className="run-brief">
      <button
        className="btn small"
        onClick={() =>
          api
            .runBrief()
            .then(() => setMsg("Started — the agent is reading the news. With a local LLM this takes ~5–10 minutes; watch the status at top right."))
            .catch((e: Error) => setMsg(e.message))
        }
      >
        {label}
      </button>
      {msg && <span className="small muted">{msg}</span>}
    </span>
  );
}

function FxPanel({ fx, note, evidence }: { fx: Fx; note: string; evidence: Brief["market"]["evidence"] }) {
  return (
    <section className="card">
      <div className="card-head">
        <h3>For an India-based investor: USD/INR</h3>
        <span className="muted small">{fx.trend} · data {fx.as_of}</span>
      </div>
      <div className="tiles">
        <StatTile label="1 USD" value={`₹${fx.rate.toFixed(2)}`} sub={`FX markup assumed ${fx.markup_pct}% each way`} />
        <StatTile label="Dollar vs rupee, 1 month" value={pct(fx.ret_1m, 2, true)} sub={`3 months ${pct(fx.ret_3m, 1, true)}`} />
        <StatTile label="Dollar vs rupee, 1 year" value={pct(fx.ret_1y, 1, true)} sub={fx.cagr != null ? `${pct(fx.cagr, 1, true)}/yr over ${fx.cagr_years}y` : undefined} />
        <StatTile label="Currency volatility" value={pct(fx.volatility_1y, 1)} sub="annualised, 1 year" />
      </div>
      <p className="small">
        <CitedText text={note} evidence={evidence} />
      </p>
      <p className="small muted">
        A rising dollar adds to your rupee returns on US stocks; a rising rupee subtracts. Your total return in INR ≈ (1 + stock return) × (1 + USD/INR
        change) − 1, minus about {2 * fx.markup_pct}% round-trip FX cost. Indian residents: remittances go through LRS (US$250k per financial year) and
        TCS may apply above the annual threshold; foreign-share gains and US dividend withholding have their own tax treatment — confirm current rules
        with your CA.
      </p>
    </section>
  );
}

// The regime's suggested exposure is the sum of weights the model handed out (it scales them by exposure).
const brief_exposure = (picks: BriefPick[]) => {
  const w = picks.map((p) => p.target_weight ?? 0).reduce((a, b) => a + b, 0);
  return w > 0 ? Math.min(1, w) : 1;
};

function InvestPlanner({ picks, fx }: { picks: BriefPick[]; fx: Fx }) {
  const [amount, setAmount] = useState(100000);
  const plan = useMemo(() => {
    const chosen = picks.filter((p) => p.verdict === "Strong pick" || p.verdict === "Pick");
    // Picks outside the model's weighted top-N get the average weight of those inside it.
    const known = chosen.map((p) => p.target_weight).filter((w): w is number => !!w);
    const avg = known.length ? known.reduce((a, b) => a + b, 0) / known.length : 0.1;
    const weights = chosen.map((p) => p.target_weight || avg);
    const total = weights.reduce((a, b) => a + b, 0);
    const exposure = Math.min(1, total, brief_exposure(picks));
    const usdPerInr = 1 / (fx.rate * (1 + fx.markup_pct / 100));
    return {
      exposure,
      rows: chosen.map((p, i) => {
        const w = (weights[i] / total) * exposure;
        const inrAmt = amount * w;
        const usd = inrAmt * usdPerInr;
        return { p, w, inrAmt, usd, shares: usd / p.price };
      }),
    };
  }, [picks, fx, amount]);

  if (!plan.rows.length) return null;
  return (
    <section className="card">
      <div className="card-head">
        <h3>Plan an investment in rupees</h3>
        <label className="amount">
          Amount&nbsp;₹
          <input type="number" min={1000} step={1000} value={amount} onChange={(e) => setAmount(Math.max(0, Number(e.target.value)))} />
        </label>
      </div>
      <p className="muted small">
        Splits your amount across today's Pick / Strong pick names using the model's risk-based weights. Cash kept aside:{" "}
        <strong>{inr(amount * (1 - plan.exposure))}</strong> ({pct(1 - plan.exposure, 0)}, from the market regime). Converted at ₹{fx.rate.toFixed(2)} +{" "}
        {fx.markup_pct}% markup. Fractional shares depend on your broker.
      </p>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Stock</th>
              <th className="num">Weight</th>
              <th className="num">Rupees</th>
              <th className="num">Dollars</th>
              <th className="num">Price</th>
              <th className="num">≈ Shares</th>
            </tr>
          </thead>
          <tbody>
            {plan.rows.map((r) => (
              <tr key={r.p.symbol}>
                <td>
                  <StockName symbol={r.p.symbol} name={r.p.name} />
                </td>
                <td className="num">{pct(r.w, 1)}</td>
                <td className="num">{inr(r.inrAmt)}</td>
                <td className="num">{usdFmt(r.usd)}</td>
                <td className="num">{usdFmt(r.p.price)}</td>
                <td className="num">{r.shares.toFixed(r.shares < 10 ? 2 : 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PickCard({ p }: { p: BriefPick }) {
  const { money } = useCurrency();
  const [showAll, setShowAll] = useState(false);
  return (
    <article className="pick card">
      <div className="card-head">
        <div>
          <h3>
            <Link to={`/stock/${p.symbol}`}>{p.symbol}</Link> <VerdictChip verdict={p.verdict} />
          </h3>
          <div className="muted small">{[p.name, p.sector, p.cap_category && `${p.cap_category} cap`].filter(Boolean).join(" · ")}</div>
        </div>
        <div className="pick-stats small">
          <RatingChip rating={p.rating} />
          <span title="Quant score + 8 × news sentiment">
            Score <strong className="num">{p.score.toFixed(0)}</strong> → <strong className="num">{p.adjusted_score.toFixed(0)}</strong> with news
          </span>
          <span>
            Conviction <strong>{p.conviction}</strong>
          </span>
          <SentimentBadge value={p.news_sentiment} label={p.sentiment_label} />
        </div>
      </div>
      <p className="thesis">
        <CitedText text={p.thesis} evidence={p.evidence} />
      </p>
      <div className="cat-risk">
        <div>
          <h4>Catalysts</h4>
          {p.catalysts.length ? (
            <ul className="pros">
              {p.catalysts.map((c) => (
                <li key={c}>
                  <CitedText text={c} evidence={p.evidence} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">None identified in recent news.</p>
          )}
        </div>
        <div>
          <h4>Risks</h4>
          {p.risks.length ? (
            <ul className="cons">
              {p.risks.map((c) => (
                <li key={c}>
                  <CitedText text={c} evidence={p.evidence} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">None flagged.</p>
          )}
        </div>
      </div>
      <h4>Evidence</h4>
      <EvidenceList items={p.evidence} />
      {!p.evidence.length && <p className="muted small">No recent articles — this pick rests on price trend and fundamentals.</p>}
      <div className="pick-foot small muted">
        <span>
          Price {money(p.price)} · stop-loss {money(p.stop_loss)} · weight {p.target_weight ? pct(p.target_weight, 1) : "—"} ·{" "}
          {p.method === "llm" ? "AI analysis" : "rules-based analysis"}
        </span>
        {p.articles.length > p.evidence.length && (
          <button className="linklike small" onClick={() => setShowAll(!showAll)}>
            {showAll ? "Hide" : `All ${p.articles.length} articles read`}
          </button>
        )}
      </div>
      {showAll && <ArticleList items={p.articles} />}
    </article>
  );
}

const ORDER: Verdict[] = ["Strong pick", "Pick", "Wait - news risk", "Watch"];
const GROUP_NOTE: Record<Verdict, string> = {
  "Strong pick": "Strong numbers and supportive news.",
  Pick: "Good numbers, news neutral to positive.",
  "Wait - news risk": "The numbers say buy, but recent news argues for patience.",
  Watch: "Not buy-rated yet.",
};

export function BriefView({ brief }: { brief: Brief }) {
  const m = brief.market;
  const groups = ORDER.map((v) => [v, brief.picks.filter((p) => p.verdict === v)] as const).filter(([, ps]) => ps.length);
  const fx = "rate" in brief.fx ? (brief.fx as Fx) : null;
  return (
    <>
      <section className="card">
        <div className="card-head">
          <div>
            <h2>Morning brief · {longDate(brief.brief_date)}</h2>
            <div className="muted small">
              Prices to {longDate(brief.run_date)} close · generated {new Date(brief.generated_at).toLocaleString()} ·{" "}
              {brief.llm.provider === "none" ? "rules-only (no LLM available)" : `${brief.llm.provider} · ${brief.llm.model}`} · {brief.stats.articles} articles (
              {Object.entries(brief.stats.by_source)
                .map(([k, v]) => `${k} ${v}`)
                .join(", ")}
              )
            </div>
          </div>
          <RegimeBadge regime={brief.regime} />
        </div>
        <p className="headline">
          <CitedText text={m.headline} evidence={m.evidence} />
        </p>
        <p>
          <CitedText text={m.market_narrative} evidence={m.evidence} />
        </p>
        {m.key_risks.length > 0 && (
          <>
            <h4>Key risks today</h4>
            <ul className="cons">
              {m.key_risks.map((r) => (
                <li key={r}>
                  <CitedText text={r} evidence={m.evidence} />
                </li>
              ))}
            </ul>
          </>
        )}
        <EvidenceList items={m.evidence} />
        <p className="small">
          <Link to="/sectors">Sector-by-sector reasoning →</Link> · <Link to="/portfolio">Exit review of your holdings →</Link>
        </p>
        {!brief.stats.finnhub_enabled && (
          <div className="callout small">
            Tip: add a free <code>FINNHUB_API_KEY</code> to <code>.env</code> for Reuters/CNBC-style wire coverage; today's news came from Yahoo Finance and SEC
            filings only.
          </div>
        )}
        {brief.llm.provider === "none" && (
          <div className="callout small">No LLM was reachable, so the reasoning below is template-based. Start Ollama (see README) or set a Claude key.</div>
        )}
      </section>

      {fx && <FxPanel fx={fx} note={m.inr_investor_note} evidence={m.evidence} />}

      <HowCalculated title="How verdicts are decided">
        <ul className="small how-list">
          <li>
            Start from the quantitative model: <Formula>score = 0.25·trend + 0.25·momentum + 0.15·relative strength + 0.10·timing + 0.15·risk + 0.10·fundamentals</Formula>
          </li>
          <li>
            News: each article's sentiment (AI, or VADER lexicon) is weighted by <Formula>trust × relevance × e^(−age/3 days)</Formula>. Adjusted score ={" "}
            <Formula>score + 8 × news sentiment</Formula>.
          </li>
          <li>
            <strong>Wait — news risk</strong>: buy-rated but news ≤ −0.3 or the AI says Avoid · <strong>Strong pick</strong>: Strong Buy, news ≥ −0.1, AI
            conviction High/Medium · <strong>Pick</strong>: other buy-rated · <strong>Watch</strong>: not buy-rated.
          </li>
          <li>Rupee planner: weights are the model's inverse-volatility weights; amount in $ = ₹ ÷ (USD/INR × (1 + markup)).</li>
        </ul>
      </HowCalculated>

      {groups.map(([verdict, ps]) => (
        <section key={verdict} className="group">
          <h3 className="group-title">
            <VerdictChip verdict={verdict} /> <span className="muted small">{GROUP_NOTE[verdict]}</span>
          </h3>
          {ps.map((p) => (
            <PickCard key={p.symbol} p={p} />
          ))}
        </section>
      ))}

      {fx && <InvestPlanner picks={brief.picks} fx={fx} />}
      {brief.errors.length > 0 && (
        <details className="small muted">
          <summary>{brief.errors.length} data issues</summary>
          {brief.errors.map((e) => (
            <div key={e}>{e}</div>
          ))}
        </details>
      )}
    </>
  );
}

export function BriefPage() {
  const b = useAsync(api.latestBrief, []);
  if (b.loading && !b.data) return <Loading label="Loading the morning brief…" />;
  if (b.error)
    return (
      <section className="card">
        <h3>No morning brief yet</h3>
        <p className="muted">{b.error}</p>
        <RunBriefButton />
      </section>
    );
  if (!b.data) return null;
  return (
    <>
      <div className="page-actions">
        <RunBriefButton label="Refresh brief" />
      </div>
      <BriefView brief={b.data} />
    </>
  );
}
