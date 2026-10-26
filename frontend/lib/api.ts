"use client";

import { useCallback, useEffect, useState } from "react";

export type DataStatus = "LIVE" | "DELAYED" | "HISTORICAL" | "SIMULATED";
export type Side = "BUY" | "SELL";

export interface Stock {
  symbol: string;
  name: string;
  exchange: string;
  sector: string;
  price: number | null;
  previous_close: number | null;
  change: number | null;
  change_pct: number | null;
  as_of: string | null;
  data_status: DataStatus;
  data_source: string;
}

export interface Quote extends Stock {
  indicators: { sma20: number | null; sma50: number | null; rsi14: number | null; volatility_20d: number | null };
  history_points: number;
}

export interface Candle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  sma20: number | null;
  sma50: number | null;
  rsi14: number | null;
}

export interface History {
  symbol: string;
  data_status: DataStatus;
  data_source: string;
  as_of: string | null;
  candles: Candle[];
}

export interface Holding {
  symbol: string;
  name: string;
  sector: string;
  quantity: number;
  avg_cost: number;
  cost_basis: number;
  price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  weight_pct: number;
  price_as_of: string | null;
}

export interface Portfolio {
  initial_cash: number;
  cash: number;
  invested: number;
  market_value: number;
  total_value: number;
  unrealized_pnl: number;
  realized_pnl: number;
  total_pnl: number;
  return_pct: number;
  holdings: Holding[];
  data_status: DataStatus;
  as_of: string | null;
  fee_percent: number;
  fee_flat: number;
}

export interface PortfolioPoint {
  date: string;
  cash: number;
  market_value: number;
  total_value: number;
}

export interface Trade {
  id: number;
  order_id: number;
  symbol: string;
  side: Side;
  quantity: number;
  price: number;
  gross_amount: number;
  fees: number;
  cash_change: number;
  realized_pnl: number | null;
  price_date: string;
  executed_at: string;
}

export interface Order {
  id: number;
  symbol: string;
  side: Side;
  quantity: number;
  status: "EXECUTED" | "REJECTED";
  reject_code: string | null;
  reject_reason: string | null;
  created_at: string;
  trade: Trade | null;
}

export interface OrderPreview {
  simulated: true;
  symbol: string;
  side: Side;
  quantity: number;
  price: number;
  price_date: string;
  gross_amount: number;
  fees: number;
  cash_change: number;
  cash_after: number;
  position_quantity_after: number;
  realized_pnl: number | null;
  fee_note: string;
}

export interface OrderResult {
  simulated: true;
  replayed: boolean;
  order: Order;
  cash: number;
}

export interface Insight {
  kind: string;
  severity: "info" | "attention";
  title: string;
  text: string;
  symbols: string[];
}

export interface Insights {
  generated_by: "rules" | "rules+llm";
  model: string | null;
  summary: string | null;
  llm_error: string | null;
  disclaimer: string;
  insights: Insight[];
  data_status: DataStatus;
  as_of: string | null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message);
  }
}

function errorMessage(body: unknown, status: number): { message: string; code?: string } {
  const detail = (body as { detail?: unknown })?.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const d = detail as { message?: string; code?: string };
    if (d.message) return { message: d.message, code: d.code };
  }
  if (Array.isArray(detail) && detail.length) {
    // FastAPI validation errors
    const first = detail[0] as { loc?: unknown[]; msg?: string };
    const field = first.loc?.slice(1).join(".");
    return { message: field ? `${field}: ${first.msg}` : (first.msg ?? "Invalid request"), code: "VALIDATION" };
  }
  if (status >= 500) return { message: "The server is unavailable. Is the backend running?" };
  return { message: `Request failed (${status})` };
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Cannot reach the server. Check that the backend is running.", 0);
  }
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    /* non-JSON body (e.g. proxy error page) */
  }
  if (!res.ok) {
    const { message, code } = errorMessage(body, res.status);
    throw new ApiError(message, res.status, code);
  }
  return body as T;
}

/** Fetch on mount and on `reload()`. Keeps the previous data while refetching (no skeleton flash). */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    setLoading(true);
    api<T>(path)
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: ApiError) => !cancelled && setError(e))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [path, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}
