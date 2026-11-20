"use client";

import { useEffect, useState } from "react";
import { ApiError, api, type BuyCheck, type SellCheck, type Side } from "@/lib/api";
import { dateLong, inr } from "@/lib/format";
import { PnL } from "./ui";

/** The pause before a trade: tax consequences of a sell, historical risk and concentration of a buy. */
export function DecisionCheck({ symbol, side, quantity }: { symbol: string; side: Side; quantity: number }) {
  const [data, setData] = useState<SellCheck | BuyCheck | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    api<SellCheck | BuyCheck>(`/api/checks/${side === "SELL" ? "sell" : "buy"}`, {
      method: "POST",
      body: JSON.stringify({ symbol, quantity }),
    })
      .then(setData)
      .catch((e: ApiError) => setError(e.message));
  }, [symbol, side, quantity]);

  return (
    <section aria-label="Decision check" className="rounded-lg border border-line p-3 text-sm">
      <h3 className="mb-2 font-semibold text-ink">Before you confirm</h3>
      {error && <p className="text-loss">{error}</p>}
      {!data && !error && <p className="text-ink-2">Checking…</p>}
      {data && side === "SELL" && <SellFacts c={data as SellCheck} />}
      {data && side === "BUY" && <BuyFacts c={data as BuyCheck} />}
    </section>
  );
}

function days(from: string, to: string) {
  return Math.round((new Date(to).getTime() - new Date(from).getTime()) / 86_400_000);
}

function SellFacts({ c }: { c: SellCheck }) {
  const shortTerm = c.pieces.filter((p) => !p.long_term);
  const best = c.options.find((o) => o.saving > 0);
  return (
    <div className="space-y-2">
      <p className="text-ink">
        {c.gain < 0 ? "Loss" : "Gain"} on this sale <PnL value={c.gain} /> · estimated tax{" "}
        <strong className="num">{inr(c.tax)}</strong>
        {c.tax > 0 && (shortTerm.some((p) => p.gain > 0) ? " (short-term, 20% + cess)" : " (long-term, 12.5% + cess)")}
      </p>
      <ul className="num space-y-0.5 text-xs text-ink-2">
        {c.pieces.map((p, i) => (
          <li key={i}>
            {p.quantity} bought {dateLong(p.buy_date)}: <PnL value={p.gain} />{" "}
            {p.long_term ? (
              <span>· long-term</span>
            ) : (
              <span>
                · short-term, long-term from {dateLong(p.long_term_from)} ({days(c.sell_date, p.long_term_from)} days)
              </span>
            )}
          </li>
        ))}
      </ul>
      {best && (
        <p className="rounded-md bg-surface-2 p-2 text-ink">
          <strong>{best.label}</strong> ({days(c.sell_date, best.sell_date)} days): estimated tax{" "}
          <span className="num">{inr(best.tax)}</span>, about <strong className="num text-gain">{inr(best.saving)} less</strong>{" "}
          if the price stays the same. The price may move either way while you wait.
        </p>
      )}
      {c.options
        .filter((o) => o.saving === 0)
        .map((o) => (
          <p key={o.label} className="text-xs text-ink-2">
            {o.label}: {o.quantity} shares, estimated tax <span className="num">{inr(o.tax)}</span>.
          </p>
        ))}
      {c.notes.map((n, i) => (
        <p key={i} className={i === 0 ? "text-ink" : "text-xs text-ink-2"}>{n}</p>
      ))}
      <p className="text-xs text-ink-2">
        {c.fy} long-term exemption left after this sale:{" "}
        <span className="num">{inr(c.fy_after.exemption_remaining)}</span> of ₹1,25,000.
      </p>
      <p className="text-[11px] text-muted">{c.disclaimer}</p>
    </div>
  );
}

function Note() {
  return <span className="mr-1 rounded bg-warn px-1 text-[10px] font-bold text-on-warn">NOTE</span>;
}

function BuyFacts({ c }: { c: BuyCheck }) {
  const span = c.history_years >= 1 ? `the last ${c.history_years} years` : "the available history";
  const flagged = new Set(c.flags.filter((f) => f.level === "attention").map((f) => f.kind));
  return (
    <div className="space-y-2">
      <ul className="space-y-1 text-ink">
        {c.max_drawdown_pct != null && (
          <li>
            {flagged.has("drawdown") && <Note />}
            In {span}, {c.symbol} fell up to <strong className="num">{Math.abs(c.max_drawdown_pct).toFixed(1)}%</strong> from a
            peak ({dateLong(c.max_drawdown_peak!)} → {dateLong(c.max_drawdown_trough!)}). On{" "}
            <span className="num">{inr(c.amount)}</span> that would be <PnL value={c.max_drawdown_rupees} />.
          </li>
        )}
        {c.worst_month_pct != null && (
          <li>
            Worst single month: <strong className="num">{c.worst_month_pct.toFixed(1)}%</strong> (from{" "}
            {dateLong(c.worst_month_start!)}), or <PnL value={c.worst_month_rupees} /> on this amount.
          </li>
        )}
        {c.losing_year_pct != null && (
          <li>
            <span className="num">{c.losing_year_pct}%</span> of 1-year holding periods in that time ended with a loss.
          </li>
        )}
        <li>
          {(flagged.has("position") || flagged.has("sector")) && <Note />}
          After this buy, {c.symbol} would be <strong className="num">{c.position_pct_after}%</strong> of your portfolio
          and {c.sector} <strong className="num">{c.sector_pct_after}%</strong>.
        </li>
      </ul>
      {c.flags
        .filter((f) => f.kind === "activity" && f.level === "attention")
        .map((f, i) => (
          <p key={i} className="rounded-md bg-surface-2 p-2 text-ink">
            <Note />
            {f.text}
          </p>
        ))}
      {c.flags
        .filter((f) => f.level === "info")
        .map((f, i) => (
          <p key={i} className="text-xs text-ink-2">{f.text}</p>
        ))}
      <p className="text-[11px] text-muted">{c.disclaimer}</p>
    </div>
  );
}
