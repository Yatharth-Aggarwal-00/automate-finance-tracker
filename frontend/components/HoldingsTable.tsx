import Link from "next/link";
import type { Holding } from "@/lib/api";
import { inr } from "@/lib/format";
import type { TradeRequest } from "./TradeDialog";
import { Button, Empty, PnL } from "./ui";

export function HoldingsTable({ holdings, onTrade }: { holdings: Holding[]; onTrade: (r: TradeRequest) => void }) {
  if (!holdings.length) {
    return (
      <Empty title="No holdings yet">
        Use <strong>New paper trade</strong> to buy your first stock with virtual cash.
      </Empty>
    );
  }
  return (
    <div className="-mx-4 overflow-x-auto sm:mx-0">
      <table className="num w-full min-w-180 text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs text-ink-2">
            <th className="py-2 pl-4 pr-2 font-medium sm:pl-0">Symbol</th>
            <th className="px-2 text-right font-medium">Qty</th>
            <th className="px-2 text-right font-medium">Avg cost</th>
            <th className="px-2 text-right font-medium">Price</th>
            <th className="px-2 text-right font-medium">Market value</th>
            <th className="px-2 text-right font-medium">Unrealized P&L</th>
            <th className="px-2 text-right font-medium">Weight</th>
            <th className="pl-2 pr-4 text-right font-medium sm:pr-0"><span className="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => (
            <tr key={h.symbol} className="border-b border-line last:border-0">
              <td className="py-2.5 pl-4 pr-2 sm:pl-0">
                <Link href={`/stocks/${h.symbol}`} className="font-medium text-ink hover:underline">{h.symbol}</Link>
                <div className="text-xs text-muted">{h.sector}</div>
              </td>
              <td className="px-2 text-right">{h.quantity}</td>
              <td className="px-2 text-right" title="Includes estimated buy charges">{inr(h.avg_cost)}</td>
              <td className="px-2 text-right">{inr(h.price)}</td>
              <td className="px-2 text-right">{inr(h.market_value)}</td>
              <td className="px-2 text-right"><PnL value={h.unrealized_pnl} pct={h.unrealized_pnl_pct} /></td>
              <td className="px-2 text-right text-ink-2">{h.weight_pct.toFixed(1)}%</td>
              <td className="whitespace-nowrap pl-2 pr-4 text-right sm:pr-0">
                <Button variant="ghost" onClick={() => onTrade({ symbol: h.symbol, side: "BUY" })}>Buy</Button>
                <Button variant="ghost" onClick={() => onTrade({ symbol: h.symbol, side: "SELL" })}>Sell</Button>
                <Button
                  variant="ghost"
                  title="Sell the whole position"
                  onClick={() => onTrade({ symbol: h.symbol, side: "SELL", quantity: h.quantity })}
                >
                  Remove
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
