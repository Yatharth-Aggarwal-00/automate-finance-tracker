"use client";

import Link from "next/link";
import { Card, Empty, ErrorState, Loading, PnL, SimulationTag } from "@/components/ui";
import { useApi, type Order, type Trade } from "@/lib/api";
import { dateLong, dateTime, inr, signedInr } from "@/lib/format";

export default function TransactionsPage() {
  const trades = useApi<Trade[]>("/api/portfolio/transactions");
  const orders = useApi<Order[]>("/api/paper-trades");
  const rejected = (orders.data ?? []).filter((o) => o.status === "REJECTED");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">Transactions</h1>
        <div className="mt-1"><SimulationTag /></div>
      </div>

      <Card title="Executed paper trades">
        {!trades.data && trades.loading && <Loading />}
        {trades.error && !trades.data && <ErrorState message={trades.error.message} onRetry={trades.reload} />}
        {trades.data && !trades.data.length && (
          <Empty title="No trades yet">Place a paper trade from the <Link href="/" className="underline">dashboard</Link>.</Empty>
        )}
        {trades.data && trades.data.length > 0 && (
          <div className="-mx-4 overflow-x-auto sm:mx-0">
            <table className="num w-full min-w-200 text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-ink-2">
                  <th className="py-2 pl-4 pr-2 font-medium sm:pl-0">Price date</th>
                  <th className="px-2 font-medium">Symbol</th>
                  <th className="px-2 font-medium">Side</th>
                  <th className="px-2 text-right font-medium">Qty</th>
                  <th className="px-2 text-right font-medium">Price</th>
                  <th className="px-2 text-right font-medium">Value</th>
                  <th className="px-2 text-right font-medium">Est. charges</th>
                  <th className="px-2 text-right font-medium">Cash change</th>
                  <th className="pl-2 pr-4 text-right font-medium sm:pr-0">Realized P&L</th>
                </tr>
              </thead>
              <tbody>
                {trades.data.map((t) => (
                  <tr key={t.id} className="border-b border-line last:border-0">
                    <td className="py-2 pl-4 pr-2 sm:pl-0" title={`Recorded ${dateTime(t.executed_at)}`}>{dateLong(t.price_date)}</td>
                    <td className="px-2"><Link href={`/stocks/${t.symbol}`} className="font-medium text-ink hover:underline">{t.symbol}</Link></td>
                    <td className="px-2">{t.side === "BUY" ? "Buy" : "Sell"}</td>
                    <td className="px-2 text-right">{t.quantity}</td>
                    <td className="px-2 text-right">{inr(t.price)}</td>
                    <td className="px-2 text-right">{inr(t.gross_amount)}</td>
                    <td className="px-2 text-right text-ink-2">{inr(t.fees)}</td>
                    <td className="px-2 text-right">{signedInr(t.cash_change)}</td>
                    <td className="pl-2 pr-4 text-right sm:pr-0">{t.realized_pnl == null ? <span className="text-muted">—</span> : <PnL value={t.realized_pnl} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Rejected orders">
        {!orders.data && orders.loading && <Loading />}
        {orders.error && !orders.data && <ErrorState message={orders.error.message} onRetry={orders.reload} />}
        {orders.data && !rejected.length && <p className="text-sm text-ink-2">No rejected orders.</p>}
        {rejected.length > 0 && (
          <ul className="divide-y divide-line text-sm">
            {rejected.map((o) => (
              <li key={o.id} className="flex flex-wrap justify-between gap-2 py-2">
                <span className="text-ink">
                  {o.side === "BUY" ? "Buy" : "Sell"} <span className="num">{o.quantity}</span> {o.symbol}
                </span>
                <span className="text-ink-2">{o.reject_reason}</span>
                <span className="text-xs text-muted">{dateTime(o.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
