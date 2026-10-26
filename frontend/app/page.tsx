"use client";

import { useState } from "react";
import { PortfolioChart } from "@/components/charts";
import { HoldingsTable } from "@/components/HoldingsTable";
import { InsightsPanel } from "@/components/InsightsPanel";
import { TradeDialog, type TradeRequest } from "@/components/TradeDialog";
import { Button, Card, DataBadge, Empty, ErrorState, Loading, PnL, StatCard } from "@/components/ui";
import { useApi, type Insights, type Portfolio, type PortfolioPoint } from "@/lib/api";
import { inr } from "@/lib/format";

export default function Dashboard() {
  const portfolio = useApi<Portfolio>("/api/portfolio");
  const history = useApi<PortfolioPoint[]>("/api/portfolio/history");
  const insights = useApi<Insights>("/api/insights");
  const [trade, setTrade] = useState<TradeRequest | null>(null);

  const refresh = () => {
    portfolio.reload();
    history.reload();
    insights.reload();
  };

  const p = portfolio.data;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-ink">Portfolio</h1>
          {p && <div className="mt-1"><DataBadge status={p.data_status} asOf={p.as_of} /></div>}
        </div>
        <Button onClick={() => setTrade({ side: "BUY" })}>New paper trade</Button>
      </div>

      {!p && portfolio.loading && <Loading />}
      {portfolio.error && !p && <ErrorState message={portfolio.error.message} onRetry={refresh} />}

      {p && (
        <div className={`space-y-6 transition-opacity ${portfolio.loading ? "opacity-60" : ""}`}>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
            <div className="col-span-2">
              <StatCard
                label="Total portfolio value"
                value={inr(p.total_value)}
                sub={<PnL value={p.total_pnl} pct={p.return_pct} />}
              />
            </div>
            <StatCard label="Available virtual cash" value={inr(p.cash)} sub={<span className="text-ink-2">of {inr(p.initial_cash)} start</span>} />
            <StatCard label="Invested (cost basis)" value={inr(p.invested)} hint="Cost of shares still held, including estimated buy charges" />
            <StatCard label="Unrealized P&L" value={<PnL value={p.unrealized_pnl} />} />
            <StatCard label="Realized P&L" value={<PnL value={p.realized_pnl} />} sub={<span className="text-ink-2">From closed (sold) shares</span>} />
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card title="Portfolio value" className="lg:col-span-2">
              {history.error && !history.data && <ErrorState message={history.error.message} onRetry={history.reload} />}
              {!history.data && history.loading && <Loading />}
              {history.data && history.data.length < 2 && (
                <Empty title="Not enough history yet">The chart appears once there are at least two days of prices.</Empty>
              )}
              {history.data && history.data.length >= 2 && <PortfolioChart points={history.data} initialCash={p.initial_cash} />}
            </Card>
            <InsightsPanel {...insights} />
          </div>

          <Card title="Holdings" actions={<span className="text-xs text-muted">Add, change or remove holdings with paper trades</span>}>
            <HoldingsTable holdings={p.holdings} onTrade={setTrade} />
          </Card>
        </div>
      )}

      {trade && <TradeDialog request={trade} onClose={() => setTrade(null)} onExecuted={refresh} />}
    </div>
  );
}
