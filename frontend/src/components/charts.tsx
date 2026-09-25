import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SectorRow, StockDetail } from "../api";
import { pct, shortDate, usd } from "../format";

const AXIS = { stroke: "var(--axis)", tick: { fill: "var(--text-muted)", fontSize: 12 }, tickLine: false };
const GRID = <CartesianGrid stroke="var(--grid)" vertical={false} />;

interface TipRow {
  name: string;
  color: string;
  value: string;
}

function TipBox({ title, rows }: { title: string; rows: TipRow[] }) {
  return (
    <div className="tip">
      <div className="tip-title">{title}</div>
      {rows.map((r) => (
        <div className="tip-row" key={r.name}>
          <span className="swatch" style={{ background: r.color }} />
          <span>{r.name}</span>
          <span className="num tip-val">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

function makeTooltip(fmt: (v: number) => string, labels: Record<string, string>) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return function Tip({ active, payload, label }: any) {
    if (!active || !payload?.length) return null;
    const rows: TipRow[] = payload
      .filter((p: { value: number | null }) => p.value != null)
      .map((p: { dataKey: string; value: number; color: string }) => ({
        name: labels[p.dataKey] ?? p.dataKey,
        color: p.color,
        value: fmt(p.value),
      }));
    return <TipBox title={shortDate(label)} rows={rows} />;
  };
}

function Legend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <div className="legend">
      {items.map((i) => (
        <span key={i.label} className="legend-item">
          <span className={`legend-line ${i.dashed ? "dashed" : ""}`} style={{ borderColor: i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}

const RANGES = { "3M": 63, "6M": 126, "1Y": 252, "2Y": 504 } as const;
type RangeKey = keyof typeof RANGES;

export function RangePicker({ value, onChange }: { value: RangeKey; onChange: (r: RangeKey) => void }) {
  return (
    <div className="seg" role="group" aria-label="Time range">
      {(Object.keys(RANGES) as RangeKey[]).map((k) => (
        <button key={k} className={k === value ? "active" : ""} onClick={() => onChange(k)} aria-pressed={k === value}>
          {k}
        </button>
      ))}
    </div>
  );
}

export function PriceAndRsi({ ind, stopLoss }: { ind: StockDetail["indicators"]; stopLoss?: number | null }) {
  const [range, setRange] = useState<RangeKey>("1Y");
  const data = useMemo(() => {
    const n = RANGES[range];
    return ind.dates.map((d, i) => ({ date: d, close: ind.close[i], sma50: ind.sma50[i], sma200: ind.sma200[i], rsi: ind.rsi14[i] })).slice(-n);
  }, [ind, range]);
  const tickEvery = Math.max(1, Math.floor(data.length / 6));
  const ticks = data.filter((_, i) => i % tickEvery === 0).map((d) => d.date);

  return (
    <div className="card">
      <div className="card-head">
        <h3>Price vs moving averages</h3>
        <RangePicker value={range} onChange={setRange} />
      </div>
      <Legend
        items={[
          { label: "Close", color: "var(--series-1)" },
          { label: "50-day avg", color: "var(--series-2)" },
          { label: "200-day avg", color: "var(--series-3)" },
          ...(stopLoss ? [{ label: "Suggested stop-loss", color: "var(--text-muted)", dashed: true }] : []),
        ]}
      />
      <div className="chart" style={{ height: 300 }}>
        <ResponsiveContainer>
          <LineChart data={data} syncId="stock" margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            {GRID}
            <XAxis dataKey="date" ticks={ticks} tickFormatter={shortDate} {...AXIS} />
            <YAxis domain={["auto", "auto"]} width={64} tickFormatter={(v) => usd(v, 0)} {...AXIS} axisLine={false} />
            <Tooltip content={makeTooltip((v) => usd(v), { close: "Close", sma50: "50-day", sma200: "200-day" })} cursor={{ stroke: "var(--axis)" }} />
            {stopLoss && <ReferenceLine y={stopLoss} stroke="var(--text-muted)" strokeDasharray="4 4" />}
            <Line dataKey="sma200" stroke="var(--series-3)" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line dataKey="sma50" stroke="var(--series-2)" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line dataKey="close" stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={false} activeDot={{ r: 4, stroke: "var(--surface)", strokeWidth: 2 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <h4 className="subchart-title">RSI (14-day) — above 70 overbought, below 30 oversold</h4>
      <div className="chart" style={{ height: 140 }}>
        <ResponsiveContainer>
          <LineChart data={data} syncId="stock" margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            {GRID}
            <ReferenceArea y1={30} y2={70} fill="var(--band)" fillOpacity={1} />
            <ReferenceLine y={70} stroke="var(--axis)" strokeDasharray="3 3" />
            <ReferenceLine y={30} stroke="var(--axis)" strokeDasharray="3 3" />
            <XAxis dataKey="date" ticks={ticks} tickFormatter={shortDate} {...AXIS} />
            <YAxis domain={[0, 100]} ticks={[30, 50, 70]} width={64} {...AXIS} axisLine={false} />
            <Tooltip content={makeTooltip((v) => v.toFixed(0), { rsi: "RSI" })} cursor={{ stroke: "var(--axis)" }} />
            <Line dataKey="rsi" stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function ScoreHistory({ history }: { history: StockDetail["history"] }) {
  if (history.length < 2) return <p className="muted">Score history appears after a few daily runs.</p>;
  return (
    <div className="chart" style={{ height: 200 }}>
      <ResponsiveContainer>
        <LineChart data={history} margin={{ top: 8, right: 76, bottom: 0, left: 0 }}>
          {GRID}
          <XAxis dataKey="run_date" tickFormatter={shortDate} minTickGap={40} {...AXIS} />
          <YAxis domain={[0, 100]} ticks={[0, 45, 65, 78, 100]} width={40} {...AXIS} axisLine={false} />
          <ReferenceLine y={78} stroke="var(--axis)" strokeDasharray="3 3" label={{ value: "Strong Buy", position: "right", fill: "var(--text-muted)", fontSize: 11 }} />
          <ReferenceLine y={65} stroke="var(--axis)" strokeDasharray="3 3" label={{ value: "Buy", position: "right", fill: "var(--text-muted)", fontSize: 11 }} />
          <ReferenceLine y={45} stroke="var(--axis)" strokeDasharray="3 3" label={{ value: "Hold", position: "right", fill: "var(--text-muted)", fontSize: 11 }} />
          <Tooltip content={makeTooltip((v) => v.toFixed(1), { score: "Score" })} cursor={{ stroke: "var(--axis)" }} />
          <Line dataKey="score" stroke="var(--series-1)" strokeWidth={2} dot={history.length < 40 ? { r: 3 } : false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Average forward return by rating group - does a higher rating actually lead to better returns? */
export function GroupReturns({ data }: { data: { group: string; value: number | null; n: number }[] }) {
  const rows = data.filter((d) => d.value != null) as { group: string; value: number; n: number }[];
  if (!rows.length) return <p className="muted">Not enough history yet for this horizon.</p>;
  return (
    <div className="chart" style={{ height: 48 + rows.length * 44 }}>
      <ResponsiveContainer>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 64, bottom: 4, left: 8 }} barCategoryGap={10}>
          <CartesianGrid stroke="var(--grid)" horizontal={false} />
          <XAxis type="number" tickFormatter={(v) => pct(v, 1)} {...AXIS} />
          <YAxis type="category" dataKey="group" width={110} {...AXIS} axisLine={false} />
          <ReferenceLine x={0} stroke="var(--axis)" />
          <Tooltip
            cursor={{ fill: "var(--band)" }}
            content={({ active, payload }) =>
              active && payload?.length ? (
                <TipBox
                  title={String(payload[0].payload.group)}
                  rows={[
                    { name: "Avg return", color: payload[0].payload.value >= 0 ? "var(--pos)" : "var(--neg)", value: pct(payload[0].payload.value, 2, true) },
                    { name: "Picks measured", color: "transparent", value: String(payload[0].payload.n) },
                  ]}
                />
              ) : null
            }
          />
          <Bar dataKey="value" radius={4} isAnimationActive={false} maxBarSize={28}>
            {rows.map((r) => (
              <Cell key={r.group} fill={r.value >= 0 ? "var(--pos)" : "var(--neg)"} />
            ))}
            <LabelList dataKey="value" position="right" formatter={(v) => pct(Number(v), 2, true)} fill="var(--text-secondary)" fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function SectorStrength({ rows }: { rows: SectorRow[] }) {
  const data = rows
    .filter((r) => r.rs_3m != null)
    .map((r) => ({ group: r.sector, value: r.rs_3m as number, rs1m: r.rs_1m, etf: r.etf }))
    .sort((a, b) => b.value - a.value);
  if (!data.length) return <p className="muted">No sector data.</p>;
  return (
    <div className="chart" style={{ height: 40 + data.length * 34 }}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 64, bottom: 4, left: 8 }} barCategoryGap={8}>
          <CartesianGrid stroke="var(--grid)" horizontal={false} />
          {/* Padding on both ends leaves room for value labels beyond the longest bars. */}
          <XAxis
            type="number"
            domain={[(min: number) => Math.min(0, min * 1.3), (max: number) => Math.max(0, max * 1.25)]}
            tickFormatter={(v) => pct(v, 0, true)}
            {...AXIS}
          />
          <YAxis type="category" dataKey="group" width={170} {...AXIS} axisLine={false} />
          <ReferenceLine x={0} stroke="var(--axis)" />
          <Tooltip
            cursor={{ fill: "var(--band)" }}
            content={({ active, payload }) =>
              active && payload?.length ? (
                <TipBox
                  title={`${payload[0].payload.group} (${payload[0].payload.etf})`}
                  rows={[
                    { name: "vs S&P, 3 months", color: payload[0].payload.value >= 0 ? "var(--pos)" : "var(--neg)", value: pct(payload[0].payload.value, 1, true) },
                    { name: "vs S&P, 1 month", color: "transparent", value: pct(payload[0].payload.rs1m, 1, true) },
                  ]}
                />
              ) : null
            }
          />
          <Bar dataKey="value" radius={4} isAnimationActive={false} maxBarSize={22}>
            {data.map((r) => (
              <Cell key={r.group} fill={r.value >= 0 ? "var(--pos)" : "var(--neg)"} />
            ))}
            <LabelList dataKey="value" position="right" formatter={(v) => pct(Number(v), 1, true)} fill="var(--text-secondary)" fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
