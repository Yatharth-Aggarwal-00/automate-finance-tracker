"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Candle, PortfolioPoint } from "@/lib/api";
import { dateLong, dateShort, inr, inrShort, num } from "@/lib/format";

const AXIS = { stroke: "var(--axis)", tick: { fill: "var(--muted)", fontSize: 11 }, tickLine: false } as const;
const GRID = { stroke: "var(--grid)", vertical: false } as const;
const CURSOR = { stroke: "var(--axis)", strokeWidth: 1 };

interface TipRow {
  name?: string | number;
  value?: number | string | null;
  color?: string;
  dataKey?: string | number;
}

function ChartTip({ active, payload, label, format = inr }: {
  active?: boolean;
  payload?: ReadonlyArray<TipRow>;
  label?: string | number;
  format?: (n: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-sm">
      <div className="mb-1 font-medium text-ink">{dateLong(String(label))}</div>
      {payload
        .filter((p) => p.value != null)
        .map((p) => (
          <div key={String(p.dataKey)} className="flex items-center gap-2 text-ink-2">
            <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
            <span>{p.name}</span>
            <span className="num ml-auto pl-3 text-ink">{format(Number(p.value))}</span>
          </div>
        ))}
    </div>
  );
}

function TableView({ children, caption }: { children: React.ReactNode; caption: string }) {
  return (
    <details className="mt-2 text-xs">
      <summary className="cursor-pointer text-ink-2 hover:text-ink">View as table</summary>
      <div className="mt-2 max-h-64 overflow-auto rounded border border-line">
        <table className="num w-full text-left">
          <caption className="sr-only">{caption}</caption>
          {children}
        </table>
      </div>
    </details>
  );
}

export function PortfolioChart({ points, initialCash }: { points: PortfolioPoint[]; initialCash: number }) {
  return (
    <div>
      <div className="h-64 w-full">
        <ResponsiveContainer>
          <AreaChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="pv" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--series-1)" stopOpacity={0.18} />
                <stop offset="100%" stopColor="var(--series-1)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid {...GRID} />
            <XAxis dataKey="date" {...AXIS} tickFormatter={dateShort} minTickGap={40} />
            <YAxis {...AXIS} axisLine={false} width={64} domain={["auto", "auto"]} tickFormatter={inrShort} />
            <ReferenceLine
              y={initialCash}
              stroke="var(--axis)"
              label={{ value: "Starting cash", position: "insideTopLeft", fill: "var(--muted)", fontSize: 11 }}
            />
            <Tooltip content={<ChartTip />} cursor={CURSOR} />
            <Area
              type="monotone"
              dataKey="total_value"
              name="Portfolio value"
              stroke="var(--series-1)"
              strokeWidth={2}
              fill="url(#pv)"
              isAnimationActive={false}
              activeDot={{ r: 4, stroke: "var(--surface)", strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <TableView caption="Daily portfolio value">
        <thead className="bg-surface-2 text-ink-2">
          <tr>
            <th className="px-2 py-1">Date</th>
            <th className="px-2 py-1 text-right">Cash</th>
            <th className="px-2 py-1 text-right">Holdings</th>
            <th className="px-2 py-1 text-right">Total</th>
          </tr>
        </thead>
        <tbody>
          {[...points].reverse().map((p) => (
            <tr key={p.date} className="border-t border-line">
              <td className="px-2 py-1">{dateLong(p.date)}</td>
              <td className="px-2 py-1 text-right">{inr(p.cash)}</td>
              <td className="px-2 py-1 text-right">{inr(p.market_value)}</td>
              <td className="px-2 py-1 text-right">{inr(p.total_value)}</td>
            </tr>
          ))}
        </tbody>
      </TableView>
    </div>
  );
}

export function PriceChart({ candles }: { candles: Candle[] }) {
  return (
    <div>
      <div className="h-72 w-full">
        <ResponsiveContainer>
          <LineChart data={candles} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid {...GRID} />
            <XAxis dataKey="date" {...AXIS} tickFormatter={dateShort} minTickGap={40} />
            <YAxis {...AXIS} axisLine={false} width={64} domain={["auto", "auto"]} tickFormatter={(v) => num(v, 0)} />
            <Tooltip content={<ChartTip />} cursor={CURSOR} />
            <Legend verticalAlign="top" align="left" height={28} iconType="plainline" wrapperStyle={{ fontSize: 12, color: "var(--ink-2)" }} />
            <Line isAnimationActive={false} type="monotone" dataKey="close" name="Close" stroke="var(--series-1)" strokeWidth={2} dot={false}
              activeDot={{ r: 4, stroke: "var(--surface)", strokeWidth: 2 }} />
            <Line isAnimationActive={false} type="monotone" dataKey="sma20" name="SMA 20" stroke="var(--series-2)" strokeWidth={1.5} dot={false}
              connectNulls={false} activeDot={{ r: 3 }} />
            <Line isAnimationActive={false} type="monotone" dataKey="sma50" name="SMA 50" stroke="var(--series-3)" strokeWidth={1.5} dot={false}
              connectNulls={false} activeDot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <TableView caption="Daily prices and moving averages">
        <thead className="bg-surface-2 text-ink-2">
          <tr>
            {["Date", "Open", "High", "Low", "Close", "SMA 20", "SMA 50", "RSI 14"].map((h, i) => (
              <th key={h} className={`px-2 py-1 ${i ? "text-right" : ""}`}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[...candles].reverse().map((c) => (
            <tr key={c.date} className="border-t border-line">
              <td className="px-2 py-1">{dateLong(c.date)}</td>
              {[c.open, c.high, c.low, c.close, c.sma20, c.sma50, c.rsi14].map((v, i) => (
                <td key={i} className="px-2 py-1 text-right">{num(v)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </TableView>
    </div>
  );
}

export function RsiChart({ candles }: { candles: Candle[] }) {
  return (
    <div className="h-40 w-full">
      <ResponsiveContainer>
        <LineChart data={candles} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="date" {...AXIS} tickFormatter={dateShort} minTickGap={40} />
          <YAxis {...AXIS} axisLine={false} width={64} domain={[0, 100]} ticks={[0, 30, 70, 100]} />
          <ReferenceLine y={70} stroke="var(--axis)"
            label={{ value: "70 · often called overbought", position: "insideTopLeft", fill: "var(--muted)", fontSize: 10 }} />
          <ReferenceLine y={30} stroke="var(--axis)"
            label={{ value: "30 · often called oversold", position: "insideBottomLeft", fill: "var(--muted)", fontSize: 10 }} />
          <Tooltip content={<ChartTip format={(n) => n.toFixed(1)} />} cursor={CURSOR} />
          <Line isAnimationActive={false} type="monotone" dataKey="rsi14" name="RSI 14" stroke="var(--series-1)" strokeWidth={2} dot={false}
            activeDot={{ r: 4, stroke: "var(--surface)", strokeWidth: 2 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
