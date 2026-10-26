"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, api, useApi, type OrderPreview, type OrderResult, type Side, type Stock } from "@/lib/api";
import { dateLong, inr, newIdempotencyKey } from "@/lib/format";
import { Button, PnL, SimulationTag } from "./ui";

type Step = "edit" | "confirm" | "done";

export interface TradeRequest {
  symbol?: string;
  side: Side;
  quantity?: number;
}

export function TradeDialog({ request, onClose, onExecuted }: {
  request: TradeRequest;
  onClose: () => void;
  onExecuted: (result: OrderResult) => void;
}) {
  const stocks = useApi<Stock[]>(request.symbol ? null : "/api/stocks");
  const [symbol, setSymbol] = useState(request.symbol ?? "");
  const [side, setSide] = useState<Side>(request.side);
  const [qtyText, setQtyText] = useState(request.quantity ? String(request.quantity) : "1");
  const [step, setStep] = useState<Step>("edit");
  const [preview, setPreview] = useState<OrderPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<OrderResult | null>(null);
  const keyRef = useRef<string | null>(null);

  const qty = /^\d+$/.test(qtyText.trim()) ? Number(qtyText) : NaN;
  const qtyValid = Number.isInteger(qty) && qty > 0 && qty <= 100000;

  useEffect(() => {
    if (!symbol && stocks.data?.length) setSymbol(stocks.data[0].symbol);
  }, [stocks.data, symbol]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !submitting && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, submitting]);

  // Server-side price preview (same calculation as execution), debounced.
  useEffect(() => {
    setPreview(null);
    if (!symbol || !qtyValid) {
      setPreviewError(symbol && qtyText ? "Enter a whole number of shares between 1 and 1,00,000." : null);
      return;
    }
    setPreviewError(null);
    const t = setTimeout(() => {
      api<OrderPreview>("/api/paper-trades/preview", {
        method: "POST",
        body: JSON.stringify({ symbol, side, quantity: qty }),
      })
        .then(setPreview)
        .catch((e: ApiError) => setPreviewError(e.message));
    }, 250);
    return () => clearTimeout(t);
  }, [symbol, side, qty, qtyValid, qtyText]);

  function review() {
    keyRef.current = newIdempotencyKey(); // one key per confirmed attempt
    setSubmitError(null);
    setStep("confirm");
  }

  async function execute() {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const r = await api<OrderResult>("/api/paper-trades", {
        method: "POST",
        headers: { "Idempotency-Key": keyRef.current ?? newIdempotencyKey() },
        body: JSON.stringify({ symbol, side, quantity: qty }),
      });
      setResult(r);
      setStep("done");
      onExecuted(r);
    } catch (e) {
      setSubmitError((e as ApiError).message);
    } finally {
      setSubmitting(false);
    }
  }

  const trade = result?.order.trade;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4" onClick={() => !submitting && onClose()}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="trade-title"
        className="w-full max-w-md rounded-t-2xl border border-line bg-surface p-5 shadow-xl sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-2">
          <div>
            <SimulationTag />
            <h2 id="trade-title" className="mt-2 text-lg font-semibold text-ink">
              {step === "done" ? "Paper order executed" : step === "confirm" ? "Confirm paper order" : "New paper order"}
            </h2>
          </div>
          <Button variant="ghost" onClick={onClose} disabled={submitting} aria-label="Close">✕</Button>
        </div>

        {step === "edit" && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-1 rounded-lg bg-surface-2 p-1" role="radiogroup" aria-label="Side">
              {(["BUY", "SELL"] as Side[]).map((s) => (
                <button
                  key={s}
                  role="radio"
                  aria-checked={side === s}
                  onClick={() => setSide(s)}
                  className={`rounded-md py-1.5 text-sm font-medium ${side === s ? "bg-surface text-ink shadow-sm" : "text-ink-2"}`}
                >
                  {s === "BUY" ? "Buy" : "Sell"}
                </button>
              ))}
            </div>

            <label className="block text-sm">
              <span className="text-ink-2">Stock</span>
              {request.symbol ? (
                <div className="mt-1 font-medium text-ink">{symbol}</div>
              ) : (
                <select
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-ink"
                >
                  {stocks.loading && !stocks.data && <option>Loading…</option>}
                  {stocks.data?.map((s) => (
                    <option key={s.symbol} value={s.symbol}>{s.symbol} — {s.name}</option>
                  ))}
                </select>
              )}
            </label>

            <label className="block text-sm">
              <span className="text-ink-2">Quantity (shares)</span>
              <input
                inputMode="numeric"
                value={qtyText}
                onChange={(e) => setQtyText(e.target.value)}
                className="num mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-ink"
                autoFocus
              />
            </label>

            <PreviewBox preview={preview} error={previewError} />

            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={onClose}>Cancel</Button>
              <Button onClick={review} disabled={!preview}>Review order</Button>
            </div>
          </div>
        )}

        {step === "confirm" && preview && (
          <div className="space-y-4">
            <p className="text-sm text-ink">
              You are placing a <strong>simulated {side === "BUY" ? "buy" : "sell"}</strong> of{" "}
              <strong className="num">{qty}</strong> {symbol} at <strong className="num">{inr(preview.price)}</strong>, the
              latest available close ({dateLong(preview.price_date)}). No real order is sent anywhere.
            </p>
            <PreviewBox preview={preview} error={null} />
            {submitError && <p role="alert" className="text-sm text-loss">{submitError}</p>}
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setStep("edit")} disabled={submitting}>Back</Button>
              <Button onClick={execute} disabled={submitting}>
                {submitting ? "Placing…" : `Confirm paper ${side === "BUY" ? "buy" : "sell"}`}
              </Button>
            </div>
          </div>
        )}

        {step === "done" && result && trade && (
          <div className="space-y-3 text-sm">
            <p className="text-ink">
              {trade.side === "BUY" ? "Bought" : "Sold"} <span className="num">{trade.quantity}</span> {trade.symbol} at{" "}
              <span className="num">{inr(trade.price)}</span> (virtual).
              {result.replayed && " This order had already been processed; it was not placed twice."}
            </p>
            {trade.realized_pnl != null && (
              <p className="text-ink-2">Realized P&L: <PnL value={trade.realized_pnl} /></p>
            )}
            <p className="text-ink-2">Virtual cash now: <span className="num text-ink">{inr(result.cash)}</span></p>
            <div className="flex justify-end">
              <Button onClick={onClose}>Done</Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function PreviewBox({ preview, error }: { preview: OrderPreview | null; error: string | null }) {
  if (error) return <p role="alert" className="rounded-lg bg-surface-2 p-3 text-sm text-loss">{error}</p>;
  if (!preview) return <p className="rounded-lg bg-surface-2 p-3 text-sm text-ink-2">Calculating…</p>;
  const rows: [string, React.ReactNode][] = [
    ["Price (latest close)", inr(preview.price)],
    ["Order value", inr(preview.gross_amount)],
    ["Estimated charges", inr(preview.fees)],
    [preview.side === "BUY" ? "Total debit" : "Net credit", inr(Math.abs(preview.cash_change))],
    ["Virtual cash after", inr(preview.cash_after)],
    ["Shares held after", preview.position_quantity_after],
  ];
  return (
    <div className="rounded-lg bg-surface-2 p-3 text-sm">
      <dl className="num grid grid-cols-2 gap-y-1">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-ink-2">{k}</dt>
            <dd className="text-right text-ink">{v}</dd>
          </div>
        ))}
        {preview.realized_pnl != null && (
          <div className="contents">
            <dt className="text-ink-2">Realized P&L (est.)</dt>
            <dd className="text-right"><PnL value={preview.realized_pnl} /></dd>
          </div>
        )}
      </dl>
      <p className="mt-2 text-xs text-muted">{preview.fee_note}. Not actual brokerage or taxes.</p>
    </div>
  );
}
