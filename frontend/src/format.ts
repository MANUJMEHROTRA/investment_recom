export const usd = (v: number | null | undefined, digits = 2) =>
  v == null ? "—" : v.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits });

export const pct = (v: number | null | undefined, digits = 1, signed = false) =>
  v == null ? "—" : `${signed && v > 0 ? "+" : ""}${(v * 100).toFixed(digits)}%`;

export const num = (v: number | null | undefined, digits = 1) => (v == null ? "—" : v.toFixed(digits));

export const compact = (v: number | null | undefined) =>
  v == null ? "—" : Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(v);

export const longDate = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" });

export const shortDate = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

export const COMPONENT_LABELS: Record<string, string> = {
  trend: "Trend",
  momentum: "Momentum",
  relative_strength: "Relative strength",
  timing: "Timing",
  risk: "Low risk",
  fundamentals: "Fundamentals",
};

/** US regular session, Mon–Fri 9:30–16:00 America/New_York (ignores holidays). */
export function isMarketOpen(now = new Date()): boolean {
  const ny = new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const mins = ny.getHours() * 60 + ny.getMinutes();
  return ny.getDay() >= 1 && ny.getDay() <= 5 && mins >= 570 && mins < 960;
}
