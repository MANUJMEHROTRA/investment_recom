import { createContext, useContext, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "./api";
import { useAsync } from "./hooks";

const Ctx = createContext<Record<string, string>>({});

export function NamesProvider({ children }: { children: ReactNode }) {
  const u = useAsync(api.universe, []);
  const names = Object.fromEntries((u.data ?? []).filter((r) => r.name).map((r) => [r.symbol, r.name as string]));
  return <Ctx.Provider value={names}>{children}</Ctx.Provider>;
}

export const useNames = () => useContext(Ctx);

/** Ticker + full company name, linked to the stock page. */
export function StockName({ symbol, name, inline = false }: { symbol: string; name?: string | null; inline?: boolean }) {
  const names = useNames();
  const full = name ?? names[symbol];
  return inline ? (
    <span className="stock-inline">
      <Link to={`/stock/${symbol}`}>
        <strong>{symbol}</strong>
      </Link>
      {full && <span className="muted"> {full}</span>}
    </span>
  ) : (
    <div className="stock-cell">
      <Link to={`/stock/${symbol}`}>
        <strong>{symbol}</strong>
      </Link>
      {full && <div className="muted small ellipsis" title={full}>{full}</div>}
    </div>
  );
}
