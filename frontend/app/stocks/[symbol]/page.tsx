"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { PriceChart, RsiChart } from "@/components/charts";
import { TradeDialog, type TradeRequest } from "@/components/TradeDialog";
import { Button, Card, DataBadge, Empty, ErrorState, Loading, PnL, StatCard } from "@/components/ui";
import { useApi, type History, type Portfolio, type Quote } from "@/lib/api";
import { inr, num } from "@/lib/format";

const RANGES = [
  { label: "1M", days: 22 },
  { label: "3M", days: 66 },
  { label: "6M", days: 132 },
  { label: "1Y", days: 260 },
];

export default function StockDetail() {
  const { symbol } = useParams<{ symbol: string }>();
  const sym = decodeURIComponent(symbol).toUpperCase();
  const [days, setDays] = useState(132);
  const quote = useApi<Quote>(`/api/stocks/${encodeURIComponent(sym)}/quote`);
  const history = useApi<History>(`/api/stocks/${encodeURIComponent(sym)}/history?days=${days}`);
  const portfolio = useApi<Portfolio>("/api/portfolio");
  const [trade, setTrade] = useState<TradeRequest | null>(null);

  if (quote.error?.status === 404) {
    return (
      <Empty title={`Unknown symbol: ${sym}`}>
        <Link href="/stocks" className="underline">Back to the stock explorer</Link>
      </Empty>
    );
  }
  if (!quote.data && quote.loading) return <Loading />;
  if (quote.error && !quote.data) return <ErrorState message={quote.error.message} onRetry={quote.reload} />;
  const q = quote.data!;
  const ind = q.indicators;
  const holding = portfolio.data?.holdings.find((h) => h.symbol === q.symbol);

  const trend =
    q.price != null && ind.sma50 != null
      ? q.price >= ind.sma50 ? "above its 50-day average" : "below its 50-day average"
      : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link href="/stocks" className="text-xs text-ink-2 hover:text-ink">← Stocks</Link>
          <h1 className="mt-1 text-2xl font-semibold text-ink">
            {q.symbol} <span className="text-base font-normal text-ink-2">{q.name}</span>
          </h1>
          <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-3xl font-semibold text-ink">{q.price == null ? "Unavailable" : inr(q.price)}</span>
            <PnL value={q.change} pct={q.change_pct} />
            <span className="text-xs text-muted">vs previous close {inr(q.previous_close)}</span>
          </div>
          <div className="mt-2"><DataBadge status={q.data_status} asOf={q.as_of} source={q.data_source} /></div>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => setTrade({ symbol: q.symbol, side: "BUY" })} disabled={q.price == null}>Paper buy</Button>
          <Button variant="secondary" onClick={() => setTrade({ symbol: q.symbol, side: "SELL" })} disabled={!holding}>
            Paper sell
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="SMA 20" value={num(ind.sma20)} sub={<span className="text-ink-2">Average close, last 20 days</span>} />
        <StatCard label="SMA 50" value={num(ind.sma50)} sub={<span className="text-ink-2">{trend ? `Price is ${trend}` : "Needs 50 days of data"}</span>} />
        <StatCard label="RSI 14" value={ind.rsi14 == null ? "—" : ind.rsi14.toFixed(1)}
          sub={<span className="text-ink-2">0–100 momentum gauge</span>} />
        <StatCard label="Volatility (20d)" value={ind.volatility_20d == null ? "—" : `${ind.volatility_20d.toFixed(1)}%`}
          sub={<span className="text-ink-2">Annualised, from daily moves</span>} />
      </div>

      <Card
        title="Price history"
        actions={
          <div className="flex gap-1" role="group" aria-label="Time range">
            {RANGES.map((r) => (
              <Button key={r.label} variant={days === r.days ? "secondary" : "ghost"} aria-pressed={days === r.days}
                onClick={() => setDays(r.days)}>
                {r.label}
              </Button>
            ))}
          </div>
        }
      >
        {history.error && !history.data && <ErrorState message={history.error.message} onRetry={history.reload} />}
        {!history.data && history.loading && <Loading />}
        {history.data && history.data.candles.length === 0 && <Empty title="No price history available" />}
        {history.data && history.data.candles.length > 0 && (
          <div className={`space-y-6 transition-opacity ${history.loading ? "opacity-60" : ""}`}>
            <PriceChart candles={history.data.candles} />
            <div>
              <h3 className="mb-1 text-xs font-medium text-ink-2">RSI 14</h3>
              <RsiChart candles={history.data.candles} />
            </div>
          </div>
        )}
        <p className="mt-3 text-xs text-muted">
          Indicators are calculated from daily closes and describe past prices only. They are not predictions.
        </p>
      </Card>

      <Card title="Your position">
        {holding ? (
          <dl className="num grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div><dt className="text-ink-2">Shares</dt><dd className="text-ink">{holding.quantity}</dd></div>
            <div><dt className="text-ink-2">Average cost</dt><dd className="text-ink">{inr(holding.avg_cost)}</dd></div>
            <div><dt className="text-ink-2">Market value</dt><dd className="text-ink">{inr(holding.market_value)}</dd></div>
            <div><dt className="text-ink-2">Unrealized P&L</dt><dd><PnL value={holding.unrealized_pnl} pct={holding.unrealized_pnl_pct} /></dd></div>
          </dl>
        ) : (
          <p className="text-sm text-ink-2">You don&apos;t hold {q.symbol} in your paper portfolio.</p>
        )}
      </Card>

      {trade && (
        <TradeDialog
          request={trade}
          onClose={() => setTrade(null)}
          onExecuted={() => {
            portfolio.reload();
          }}
        />
      )}
    </div>
  );
}
