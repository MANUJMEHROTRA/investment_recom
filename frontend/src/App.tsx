import { useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { api, getApiBase, setApiBase } from "./api";
import { CurrencyProvider, CurrencyToggle } from "./currency";
import { useAsync } from "./hooks";
import { NamesProvider } from "./names";
import { Backtest } from "./pages/Backtest";
import { BriefPage } from "./pages/Brief";
import { Glossary } from "./pages/Glossary";
import { Social } from "./pages/Social";
import { Portfolio } from "./pages/Portfolio";
import { Sectors } from "./pages/Sectors";
import { Dashboard } from "./pages/Dashboard";
import { History, HistoryDay } from "./pages/History";
import { Method } from "./pages/Method";
import { PerformancePage } from "./pages/Performance";
import { Stock } from "./pages/Stock";

function Connection() {
  const health = useAsync(api.health, [], 15_000);
  const [editing, setEditing] = useState(false);
  const [url, setUrl] = useState(getApiBase());
  const ok = health.data?.status === "ok";
  const job = health.data?.job;

  return (
    <div className="connection">
      <button className="linklike conn-status" onClick={() => setEditing(!editing)} title="Backend connection settings">
        <span className={`dot ${health.error ? "down" : ok ? "up" : "warn"}`} aria-hidden />
        {health.error ? "Backend offline" : job?.running ? `Working: ${job.message}` : ok ? "Connected" : "Degraded"}
      </button>
      {editing && (
        <form
          className="conn-form"
          onSubmit={(e) => {
            e.preventDefault();
            setApiBase(url);
            window.location.reload();
          }}
        >
          <label htmlFor="api">Backend URL (your machine)</label>
          <input id="api" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://localhost:8000" />
          <button className="btn small">Save</button>
          {health.error && <p className="small">{health.error}</p>}
          {job?.error && <p className="small down">Last job failed: {job.error}</p>}
          {health.data && (
            <p className="small muted">
              {health.data.price_rows.toLocaleString()} price rows · last market day {health.data.last_market_date ?? "—"}
              <br />
              News agent: {health.data.agent.status === "ok" ? `${health.data.agent.llm_provider} (${health.data.agent.llm_model})` : "offline"} · last brief{" "}
              {health.data.last_brief_date ?? "—"}
              <br />
              Next brief {health.data.next_brief ?? "—"} · next close-of-day run {health.data.next_scheduled_run ?? "—"}
            </p>
          )}
        </form>
      )}
    </div>
  );
}

export default function App() {
  return (
    <CurrencyProvider>
      <NamesProvider>
        <Shell />
      </NamesProvider>
    </CurrencyProvider>
  );
}

function Shell() {
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden>
            <rect width="32" height="32" rx="7" fill="var(--series-1)" />
            <path d="M7 22l6-6 4 4 8-9" stroke="#fff" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Stock Compass
        </div>
        <nav>
          <NavLink to="/" end>
            Brief
          </NavLink>
          <NavLink to="/picks">Picks</NavLink>
          <NavLink to="/sectors">Sectors</NavLink>
          <NavLink to="/social">Social</NavLink>
          <NavLink to="/portfolio">Portfolio</NavLink>
          <NavLink to="/backtest">Backtest</NavLink>
          <NavLink to="/performance">Track record</NavLink>
          <NavLink to="/history">History</NavLink>
          <NavLink to="/method">Method</NavLink>
          <NavLink to="/glossary">Glossary</NavLink>
        </nav>
        <div className="topbar-right">
          <CurrencyToggle />
          <Connection />
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<BriefPage />} />
          <Route path="/picks" element={<Dashboard />} />
          <Route path="/sectors" element={<Sectors />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/social" element={<Social />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/glossary" element={<Glossary />} />
          <Route path="/history" element={<History />} />
          <Route path="/history/:date" element={<HistoryDay />} />
          <Route path="/stock/:symbol" element={<Stock />} />
          <Route path="/performance" element={<PerformancePage />} />
          <Route path="/method" element={<Method />} />
        </Routes>
      </main>
      <footer className="footer muted small">
        Personal research tool · data from Yahoo Finance (free, delayed) · stored only in your local Postgres · not financial advice.
      </footer>
    </div>
  );
}
