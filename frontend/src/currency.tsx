import { createContext, useContext, useState, type ReactNode } from "react";
import { api, type Fx } from "./api";
import { useAsync } from "./hooks";

type Currency = "USD" | "INR";

interface CurrencyCtx {
  currency: Currency;
  setCurrency: (c: Currency) => void;
  fx: Fx | null;
  /** Format a USD amount in the selected display currency. */
  money: (usd: number | null | undefined, digits?: number) => string;
}

const Ctx = createContext<CurrencyCtx | null>(null);
const KEY = "currency";

function load(): Currency {
  try {
    return localStorage.getItem(KEY) === "INR" ? "INR" : "USD";
  } catch {
    return "USD";
  }
}

export const inr = (v: number | null | undefined, digits = 0) =>
  v == null ? "—" : v.toLocaleString("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: digits, maximumFractionDigits: digits });

export const usdFmt = (v: number | null | undefined, digits = 2) =>
  v == null ? "—" : v.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits });

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const [currency, setState] = useState<Currency>(load);
  const fx = useAsync(api.fx, []);
  const setCurrency = (c: Currency) => {
    setState(c);
    try {
      localStorage.setItem(KEY, c);
    } catch {
      /* ignore */
    }
  };
  const rate = fx.data?.rate;
  const money = (usd: number | null | undefined, digits = 2) =>
    currency === "INR" && rate ? inr(usd == null ? null : usd * rate, usd != null && Math.abs(usd * rate) < 1000 ? 2 : 0) : usdFmt(usd, digits);
  return <Ctx.Provider value={{ currency, setCurrency, fx: fx.data, money }}>{children}</Ctx.Provider>;
}

export function useCurrency(): CurrencyCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useCurrency outside CurrencyProvider");
  return c;
}

export function CurrencyToggle() {
  const { currency, setCurrency, fx } = useCurrency();
  return (
    <div className="seg" role="group" aria-label="Display currency" title={fx ? `1 USD = ₹${fx.rate.toFixed(2)} (${fx.as_of})` : "USD/INR not loaded yet"}>
      {(["USD", "INR"] as const).map((c) => (
        <button key={c} className={c === currency ? "active" : ""} onClick={() => setCurrency(c)} aria-pressed={c === currency} disabled={c === "INR" && !fx}>
          {c === "USD" ? "$ USD" : "₹ INR"}
        </button>
      ))}
    </div>
  );
}
