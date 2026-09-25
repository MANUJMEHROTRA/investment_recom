import { useMemo, useState } from "react";
import { CATEGORIES, GLOSSARY, type Category } from "../glossary";

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-");

export function Glossary() {
  const [q, setQ] = useState("");
  const [cat, setCat] = useState<Category | "all">("all");
  const terms = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return GLOSSARY.filter(
      (t) =>
        (cat === "all" || t.category === cat) &&
        (!needle || [t.term, t.aka, t.what, t.formula, t.read].some((f) => f?.toLowerCase().includes(needle))),
    );
  }, [q, cat]);

  return (
    <>
      <section className="card">
        <div className="card-head">
          <div>
            <h2>Glossary & calculations</h2>
            <div className="muted small">
              Every number on this dashboard, how it is computed and how to read it. Start with <strong>Prerequisites</strong> if you are new to investing.
            </div>
          </div>
          <input className="search" placeholder="Search e.g. momentum, P/E, UMAP…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search glossary" />
        </div>
        <div className="chips-row" role="group" aria-label="Category">
          <button className={`pill ${cat === "all" ? "active" : ""}`} onClick={() => setCat("all")}>
            All ({GLOSSARY.length})
          </button>
          {CATEGORIES.map((c) => (
            <button key={c} className={`pill ${cat === c ? "active" : ""}`} onClick={() => setCat(c)}>
              {c}
            </button>
          ))}
        </div>
      </section>

      {CATEGORIES.filter((c) => terms.some((t) => t.category === c)).map((c) => (
        <section className="card" key={c}>
          <h3>{c}</h3>
          <dl className="glossary">
            {terms
              .filter((t) => t.category === c)
              .map((t) => (
                <div key={t.term} id={slug(t.term)} className="gterm">
                  <dt>
                    {t.term}
                    {t.aka && <span className="muted small"> · {t.aka}</span>}
                  </dt>
                  <dd>
                    <p>{t.what}</p>
                    {t.formula && <code className="formula">{t.formula}</code>}
                    {t.example && (
                      <p className="small">
                        <strong>Example:</strong> {t.example}
                      </p>
                    )}
                    {t.read && (
                      <p className="small">
                        <strong>How to read it:</strong> {t.read}
                      </p>
                    )}
                    {t.usedIn && <p className="small muted">Used in: {t.usedIn}</p>}
                  </dd>
                </div>
              ))}
          </dl>
        </section>
      ))}
      {!terms.length && <p className="muted">No terms match “{q}”.</p>}
    </>
  );
}
