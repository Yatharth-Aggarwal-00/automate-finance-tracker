"use client";

import type { TaxSummary } from "@/lib/api";
import { dateLong, inr } from "@/lib/format";
import { Card, ErrorState, Loading, PnL } from "./ui";

const SOON_DAYS = 60;

export function TaxCard({ data, error, loading, reload }: {
  data: TaxSummary | null;
  error: { message: string } | null;
  loading: boolean;
  reload: () => void;
}) {
  return (
    <Card title={data ? `Tax & timing · ${data.fy}` : "Tax & timing"}>
      {!data && loading && <Loading />}
      {error && !data && <ErrorState message={error.message} onRetry={reload} />}
      {data && <TaxBody s={data} dim={loading} />}
    </Card>
  );
}

function TaxBody({ s, dim }: { s: TaxSummary; dim: boolean }) {
  const e = s.estimate;
  const exemption = s.rates.ltcg_exemption;
  const usedPct = Math.min(100, (e.exemption_used / exemption) * 100);
  const within = s.lots.filter((l) => l.days_to_long_term > 0 && l.days_to_long_term <= SOON_DAYS);
  const soon = within.filter((l) => l.extra_tax_if_sold_today > 0);
  const lossSoon = within.filter((l) => l.unrealized_gain < 0);

  return (
    <div className={`grid gap-6 transition-opacity md:grid-cols-2 ${dim ? "opacity-60" : ""}`}>
      <div className="space-y-3 text-sm">
        <dl className="num grid grid-cols-3 gap-2">
          <div>
            <dt className="text-xs text-ink-2">Short-term gains</dt>
            <dd><PnL value={e.short_term_net} /></dd>
          </div>
          <div>
            <dt className="text-xs text-ink-2">Long-term gains</dt>
            <dd><PnL value={e.long_term_net} /></dd>
          </div>
          <div>
            <dt className="text-xs text-ink-2">Estimated tax</dt>
            <dd className="font-semibold text-ink">{inr(e.tax)}</dd>
          </div>
        </dl>
        <div>
          <div className="flex justify-between text-xs text-ink-2">
            <span>Long-term exemption used</span>
            <span className="num">{inr(e.exemption_used)} of {inr(exemption)}</span>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={Math.round(usedPct)}
            aria-valuemin={0} aria-valuemax={100} aria-label="Long-term exemption used">
            <div className="h-full rounded-full bg-accent" style={{ width: `${usedPct}%` }} />
          </div>
        </div>
        {s.harvestable_ltcg > 0 && (
          <p className="rounded-md bg-surface-2 p-2 text-ink">
            <strong className="num">{inr(s.harvestable_ltcg)}</strong> of your unrealised long-term gains fit inside this
            year&apos;s remaining exemption. Booking them before {dateLong(s.fy_end)} ({s.days_left_in_fy} days) would be
            tax-free. Selling and re-buying resets your purchase price; charges apply.
          </p>
        )}
      </div>

      <div className="text-sm">
        <h3 className="mb-2 text-xs font-medium text-ink-2">Turning long-term soon</h3>
        {soon.length === 0 && lossSoon.length === 0 ? (
          <p className="text-ink-2">No holdings turn long-term in the next {SOON_DAYS} days.</p>
        ) : (
          <ul className="space-y-2">
            {soon.map((l) => (
              <li key={`${l.symbol}-${l.buy_date}`} className="rounded-md bg-surface-2 p-2">
                <div className="font-medium text-ink">
                  {l.symbol} · {l.quantity} shares · long-term on {dateLong(l.long_term_from)}{" "}
                  <span className="text-ink-2">({l.days_to_long_term} days)</span>
                </div>
                <div className="num text-ink-2">
                  Selling before then would cost about <strong className="text-loss">{inr(l.extra_tax_if_sold_today)}</strong>{" "}
                  more tax at today&apos;s price.
                </div>
              </li>
            ))}
            {lossSoon.map((l) => (
              <li key={`${l.symbol}-${l.buy_date}-loss`} className="rounded-md bg-surface-2 p-2">
                <div className="font-medium text-ink">
                  {l.symbol} · {l.quantity} shares · long-term on {dateLong(l.long_term_from)}{" "}
                  <span className="text-ink-2">({l.days_to_long_term} days)</span>
                </div>
                <div className="num text-ink-2">
                  Currently a loss of <PnL value={l.unrealized_gain} />. If you were going to sell anyway, selling before then
                  keeps it a short-term loss, which can offset any gains; afterwards it offsets only long-term gains.
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-[11px] text-muted">{s.disclaimer}</p>
      </div>
    </div>
  );
}
