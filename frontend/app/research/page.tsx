"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { EquityChart } from "@/components/charts";
import { Button, Card, ErrorState, Loading } from "@/components/ui";
import {
  ApiError,
  api,
  useApi,
  type BacktestResponse,
  type FactorInfo,
  type FactorsResponse,
  type PerfMetrics,
  type PeriodResult,
  type ScreenResponse,
} from "@/lib/api";
import { dateLong } from "@/lib/format";

const pct = (v: number | null | undefined, signed = false) =>
  v == null ? "—" : `${signed && v > 0 ? "+" : ""}${v.toFixed(1)}%`;
const fix = (v: number | null | undefined, d = 2) => (v == null ? "—" : v.toFixed(d));

export default function ResearchPage() {
  const factors = useApi<FactorsResponse>("/api/quant/factors");
  const [weights, setWeights] = useState<Record<string, number>>({ mom_12_1: 1 });
  const [topN, setTopN] = useState(15);
  const [costBps, setCostBps] = useState(20);
  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [screen, setScreen] = useState<ScreenResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  async function run() {
    setRunning(true);
    setRunError(null);
    try {
      const body = JSON.stringify({ weights, top_n: topN, cost_bps: costBps });
      const [bt, sc] = await Promise.all([
        api<BacktestResponse>("/api/quant/backtest", { method: "POST", body }),
        api<ScreenResponse>("/api/quant/screen", { method: "POST", body: JSON.stringify({ weights }) }),
      ]);
      setResult(bt);
      setScreen(sc);
    } catch (e) {
      setRunError((e as ApiError).message);
    } finally {
      setRunning(false);
    }
  }

  // Run the default model once the factor research has loaded.
  useEffect(() => {
    if (factors.data && !result && !running) void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [factors.data]);

  const f = factors.data;
  const names = Object.fromEntries((f?.factors ?? []).map((x) => [x.key, x.name]));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">Quant research</h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-2">
          Which price signals actually predicted Indian stock returns? Each factor ranks stocks every month-end, and is
          tested against the following month&apos;s returns. The last 3 years are kept as an out-of-sample check.
        </p>
        {f && (
          <p className="mt-2 text-xs text-muted">
            {f.universe_size} stocks (today&apos;s Nifty 100) · {dateLong(f.start)} → {dateLong(f.end)} ·{" "}
            {f.rebalances} monthly rebalances · out-of-sample from {dateLong(f.test_start)} · source: {f.data_source}
          </p>
        )}
      </div>

      {!f && factors.loading && <Loading label="Computing factor research (first run takes a few seconds)…" />}
      {factors.error && !f && <ErrorState message={factors.error.message} onRetry={factors.reload} />}

      {f && (
        <>
          <Card title="Read this first">
            <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">
              {f.caveats.map((c, i) => <li key={i}>{c}</li>)}
            </ul>
          </Card>

          <Card title="Factor evidence" actions={<span className="text-xs text-muted">Tick factors to combine them into a model below</span>}>
            <FactorTable factors={f.factors} weights={weights} setWeights={setWeights} />
            <p className="mt-3 text-xs text-muted">
              IC = rank correlation between the factor and next month&apos;s return (0 = no skill). t ≥ 2 is the usual bar
              for evidence. Spread = top-fifth minus bottom-fifth of stocks, per year. Verdicts need t ≥ 2 before{" "}
              {dateLong(f.test_start)} and the same direction afterwards.
            </p>
          </Card>

          <Card
            title="Backtest the model"
            actions={
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <label className="flex items-center gap-1 text-ink-2">
                  Hold top
                  <select value={topN} onChange={(e) => setTopN(Number(e.target.value))}
                    className="rounded border border-line bg-surface px-1 py-0.5 text-ink">
                    {[5, 10, 15, 20, 30].map((n) => <option key={n}>{n}</option>)}
                  </select>
                </label>
                <label className="flex items-center gap-1 text-ink-2">
                  Cost per side
                  <select value={costBps} onChange={(e) => setCostBps(Number(e.target.value))}
                    className="rounded border border-line bg-surface px-1 py-0.5 text-ink">
                    {[0, 10, 20, 30, 50].map((b) => <option key={b} value={b}>{(b / 100).toFixed(2)}%</option>)}
                  </select>
                </label>
                <Button onClick={run} disabled={running || Object.keys(weights).length === 0}>
                  {running ? "Running…" : "Run backtest"}
                </Button>
              </div>
            }
          >
            <p className="mb-3 text-sm text-ink-2">
              Model: {Object.keys(weights).length === 0 ? "pick at least one factor above" : Object.entries(weights)
                .map(([k, w]) => `${names[k] ?? k}${Object.keys(weights).length > 1 ? ` ×${w}` : ""}`).join(" + ")}. Each
              month-end, buy the top {topN} stocks by the combined score in equal amounts and hold for a month.
            </p>
            {runError && <ErrorState message={runError} onRetry={run} />}
            {!result && running && <Loading label="Backtesting…" />}
            {result && (
              <div className={`space-y-6 transition-opacity ${running ? "opacity-60" : ""}`}>
                <Verdict r={result} />
                <EquityChart points={result.curve} testStart={result.test_start} />
                <ResultsTable r={result} />
                <p className="text-xs text-muted">
                  Sharpe uses a {result.risk_free_pct}% risk-free rate. Costs: {result.cost_per_side_pct}% per buy or sell,
                  covering brokerage, STT, exchange charges and slippage roughly. Latest model holdings
                  ({result.latest_date ? dateLong(result.latest_date) : "—"}): {result.latest_holdings.join(", ")}.
                </p>
              </div>
            )}
          </Card>

          {screen && <ScreenTable s={screen} names={names} />}
        </>
      )}
    </div>
  );
}

function FactorTable({ factors, weights, setWeights }: {
  factors: FactorInfo[];
  weights: Record<string, number>;
  setWeights: (w: Record<string, number>) => void;
}) {
  const toggle = (k: string) => {
    const next = { ...weights };
    if (k in next) delete next[k];
    else next[k] = 1;
    setWeights(next);
  };
  return (
    <div className="-mx-4 overflow-x-auto sm:mx-0">
      <table className="num w-full min-w-200 text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs text-ink-2">
            <th className="py-2 pl-4 pr-2 font-medium sm:pl-0">Use</th>
            <th className="px-2 font-medium">Factor</th>
            <th className="px-2 text-right font-medium">IC (t) before</th>
            <th className="px-2 text-right font-medium">IC (t) last 3y</th>
            <th className="px-2 text-right font-medium">Months IC &gt; 0</th>
            <th className="px-2 text-right font-medium">Spread/yr before</th>
            <th className="px-2 text-right font-medium">Spread/yr last 3y</th>
            <th className="pl-2 pr-4 font-medium sm:pr-0">Verdict</th>
          </tr>
        </thead>
        <tbody>
          {factors.map((x) => (
            <tr key={x.key} className="border-b border-line align-top last:border-0">
              <td className="py-2 pl-4 pr-2 sm:pl-0">
                <input type="checkbox" aria-label={`Use ${x.name}`} checked={x.key in weights} onChange={() => toggle(x.key)} />
              </td>
              <td className="px-2 py-2">
                <div className="font-medium text-ink">{x.name}</div>
                <div className="max-w-xs text-xs text-muted">{x.description}</div>
              </td>
              <td className="px-2 py-2 text-right">{fix(x.train.ic_mean, 3)} <span className="text-ink-2">({fix(x.train.ic_t, 1)})</span></td>
              <td className="px-2 py-2 text-right">{fix(x.test.ic_mean, 3)} <span className="text-ink-2">({fix(x.test.ic_t, 1)})</span></td>
              <td className="px-2 py-2 text-right">{pct(x.full.hit_rate)}</td>
              <td className="px-2 py-2 text-right">{pct(x.train.spread_annual, true)}</td>
              <td className="px-2 py-2 text-right">{pct(x.test.spread_annual, true)}</td>
              <td className="py-2 pl-2 pr-4 sm:pr-0">
                <span className={`rounded-full border border-line px-2 py-0.5 text-xs ${x.verdict === "Held up out of sample" ? "bg-surface-2 font-medium text-ink" : "text-ink-2"}`}>
                  {x.verdict}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Verdict({ r }: { r: BacktestResponse }) {
  const t = r.test.vs_equal_weight;
  const tr = r.train.vs_equal_weight;
  if (t.excess_cagr == null || tr.excess_cagr == null) return null;
  const held = tr.excess_cagr > 0 && t.excess_cagr > 0;
  return (
    <p className="rounded-md bg-surface-2 p-3 text-sm text-ink">
      Against the equal-weight universe (the fair benchmark), this model returned{" "}
      <strong>{pct(tr.excess_cagr, true)} a year</strong> before {dateLong(r.test_start)} and{" "}
      <strong>{pct(t.excess_cagr, true)} a year</strong> in the last 3 years, after costs.{" "}
      {held
        ? "It beat the universe in both periods, but check whether the factor evidence above is statistically reliable before trusting it."
        : "It did not beat the universe consistently, so there is no evidence of an edge."}
    </p>
  );
}

const PERIODS: { key: "full" | "train" | "test"; label: string }[] = [
  { key: "full", label: "Whole period" },
  { key: "train", label: "Before (tuning)" },
  { key: "test", label: "Last 3 years" },
];

function ResultsTable({ r }: { r: BacktestResponse }) {
  const rows: { label: string; get: (p: PerfMetrics) => string }[] = [
    { label: "CAGR", get: (m) => pct(m.cagr) },
    { label: "Volatility", get: (m) => pct(m.volatility) },
    { label: "Sharpe ratio", get: (m) => fix(m.sharpe) },
    { label: "Max drawdown", get: (m) => pct(m.max_drawdown) },
  ];
  const rel = (p: PeriodResult) => [
    ["vs equal-weight universe", `${pct(p.vs_equal_weight.excess_cagr, true)}/yr · beat ${pct(p.vs_equal_weight.beat_months_pct)} of months · IR ${fix(p.vs_equal_weight.information_ratio)}`],
    ["vs Nifty 50", p.vs_nifty ? `${pct(p.vs_nifty.excess_cagr, true)}/yr · beat ${pct(p.vs_nifty.beat_months_pct)} of months` : "—"],
    ["Monthly turnover", pct(p.avg_turnover)],
  ];
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {PERIODS.map(({ key, label }) => {
        const p = r[key];
        return (
          <div key={key} className="rounded-lg border border-line p-3">
            <h3 className="mb-2 text-sm font-semibold text-ink">
              {label} <span className="font-normal text-muted">({p.strategy.months} months)</span>
            </h3>
            <table className="num w-full text-xs">
              <thead>
                <tr className="text-left text-ink-2">
                  <th className="py-1 font-medium" />
                  <th className="py-1 text-right font-medium">Model</th>
                  <th className="py-1 text-right font-medium">Equal-wt</th>
                  <th className="py-1 text-right font-medium">Nifty 50</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.label} className="border-t border-line">
                    <td className="py-1 text-ink-2">{row.label}</td>
                    <td className="py-1 text-right font-medium text-ink">{row.get(p.strategy)}</td>
                    <td className="py-1 text-right">{row.get(p.equal_weight)}</td>
                    <td className="py-1 text-right">{p.nifty ? row.get(p.nifty) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <dl className="mt-2 space-y-1 text-xs">
              {rel(p).map(([k, v]) => (
                <div key={k}>
                  <dt className="inline text-ink-2">{k}: </dt>
                  <dd className="num inline text-ink">{v}</dd>
                </div>
              ))}
            </dl>
          </div>
        );
      })}
    </div>
  );
}

function ScreenTable({ s, names }: { s: ScreenResponse; names: Record<string, string> }) {
  const [all, setAll] = useState(false);
  const keys = Object.keys(s.weights);
  const rows = all ? s.rows : s.rows.slice(0, 20);
  return (
    <Card title={`Today's ranking · ${dateLong(s.as_of)}`} actions={<span className="text-xs text-muted">Same factor mix as the model</span>}>
      <p className="mb-3 text-sm text-ink-2">{s.disclaimer}</p>
      <div className="-mx-4 overflow-x-auto sm:mx-0">
        <table className="num w-full min-w-150 text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-ink-2">
              <th className="py-2 pl-4 pr-2 font-medium sm:pl-0">#</th>
              <th className="px-2 font-medium">Stock</th>
              <th className="px-2 font-medium">Sector</th>
              <th className="px-2 text-right font-medium">Score</th>
              {keys.map((k) => <th key={k} className="pl-2 pr-4 text-right font-medium sm:pr-0">{names[k] ?? k} pct.</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.symbol} className="border-b border-line last:border-0">
                <td className="py-2 pl-4 pr-2 text-ink-2 sm:pl-0">{r.rank}</td>
                <td className="px-2"><Link href={`/stocks/${encodeURIComponent(r.symbol)}`} className="font-medium text-ink hover:underline">{r.symbol}</Link></td>
                <td className="px-2 text-ink-2">{r.sector}</td>
                <td className="px-2 text-right">{r.score.toFixed(2)}</td>
                {keys.map((k) => <td key={k} className="pl-2 pr-4 text-right sm:pr-0">{r.percentiles[k] == null ? "—" : r.percentiles[k]}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {s.rows.length > 20 && (
        <Button variant="ghost" className="-ml-3 mt-2" onClick={() => setAll((v) => !v)}>
          {all ? "Show top 20" : `Show all ${s.rows.length}`}
        </Button>
      )}
    </Card>
  );
}
