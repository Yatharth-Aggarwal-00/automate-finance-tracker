"use client";

import Link from "next/link";
import { useState } from "react";
import { Card, DataBadge, Empty, ErrorState, Loading, PnL } from "@/components/ui";
import { useApi, type Stock } from "@/lib/api";
import { inr } from "@/lib/format";

export default function StocksPage() {
  const [q, setQ] = useState("");
  const stocks = useApi<Stock[]>("/api/stocks");
  const list = (stocks.data ?? []).filter(
    (s) => !q || s.symbol.toLowerCase().includes(q.toLowerCase()) || s.name.toLowerCase().includes(q.toLowerCase()),
  );
  const first = stocks.data?.[0];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">Stock explorer</h1>
        {first && <div className="mt-1"><DataBadge status={first.data_status} asOf={first.as_of} source={first.data_source} /></div>}
      </div>
      <Card
        title="Watchlist"
        actions={
          <input
            placeholder="Search symbol or name"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="w-full rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink sm:w-64"
          />
        }
      >
        {!stocks.data && stocks.loading && <Loading />}
        {stocks.error && !stocks.data && <ErrorState message={stocks.error.message} onRetry={stocks.reload} />}
        {stocks.data && !list.length && <Empty title="No matching stocks" />}
        {list.length > 0 && (
          <div className="-mx-4 overflow-x-auto sm:mx-0">
            <table className="num w-full min-w-150 text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-ink-2">
                  <th className="py-2 pl-4 pr-2 font-medium sm:pl-0">Symbol</th>
                  <th className="px-2 font-medium">Sector</th>
                  <th className="px-2 text-right font-medium">Latest close</th>
                  <th className="px-2 text-right font-medium">Previous close</th>
                  <th className="pl-2 pr-4 text-right font-medium sm:pr-0">Change</th>
                </tr>
              </thead>
              <tbody>
                {list.map((s) => (
                  <tr key={s.symbol} className="border-b border-line last:border-0 hover:bg-surface-2">
                    <td className="py-2.5 pl-4 pr-2 sm:pl-0">
                      <Link href={`/stocks/${s.symbol}`} className="font-medium text-ink hover:underline">{s.symbol}</Link>
                      <div className="text-xs text-muted">{s.name}</div>
                    </td>
                    <td className="px-2 text-ink-2">{s.sector}</td>
                    <td className="px-2 text-right">{s.price == null ? <span className="text-muted">Unavailable</span> : inr(s.price)}</td>
                    <td className="px-2 text-right">{inr(s.previous_close)}</td>
                    <td className="pl-2 pr-4 text-right sm:pr-0"><PnL value={s.change} pct={s.change_pct} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
