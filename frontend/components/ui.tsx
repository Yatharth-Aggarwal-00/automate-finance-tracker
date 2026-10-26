import type { ReactNode } from "react";
import type { DataStatus } from "@/lib/api";
import { dateTime, signedInr, signedPct } from "@/lib/format";

export function Card({ title, actions, children, className = "" }: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-line bg-surface p-4 sm:p-5 ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function StatCard({ label, value, sub, hint }: { label: string; value: ReactNode; sub?: ReactNode; hint?: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4" title={hint}>
      <div className="text-xs text-ink-2">{label}</div>
      <div className="mt-1 text-xl font-semibold text-ink sm:text-2xl">{value}</div>
      {sub && <div className="mt-1 text-xs">{sub}</div>}
    </div>
  );
}

const STATUS_TEXT: Record<DataStatus, string> = {
  SIMULATED: "Simulated data",
  HISTORICAL: "Historical EOD data",
  DELAYED: "Delayed data",
  LIVE: "Live data",
};

/** Data provenance: always shows the label and the timestamp of the latest price. */
export function DataBadge({ status, asOf, source }: { status: DataStatus; asOf: string | null; source?: string }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-2">
      <span className="rounded-full border border-line bg-surface-2 px-2 py-0.5 font-medium text-ink">
        {STATUS_TEXT[status]}
      </span>
      <span>{asOf ? `Prices as of ${dateTime(asOf)}` : "No price timestamp"}</span>
      {source && <span className="text-muted">· source: {source}</span>}
    </span>
  );
}

/** Gain/loss text. Direction is carried by sign and arrow as well as color. */
export function PnL({ value, pct, className = "" }: { value: number | null; pct?: number | null; className?: string }) {
  if (value == null) return <span className="text-muted">—</span>;
  const tone = value > 0 ? "text-gain" : value < 0 ? "text-loss" : "text-ink-2";
  const arrow = value > 0 ? "▲" : value < 0 ? "▼" : "";
  return (
    <span className={`num whitespace-nowrap ${tone} ${className}`}>
      {arrow && <span aria-hidden className="mr-0.5 text-[0.75em]">{arrow}</span>}
      {signedInr(value)}
      {pct != null && <span className="ml-1">({signedPct(pct)})</span>}
    </span>
  );
}

export function Button({ variant = "primary", className = "", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
}) {
  const styles = {
    primary: "bg-accent text-on-accent hover:opacity-90",
    secondary: "border border-line bg-surface text-ink hover:bg-surface-2",
    ghost: "text-ink-2 hover:bg-surface-2 hover:text-ink",
  }[variant];
  return (
    <button
      className={`inline-flex items-center justify-center rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`}
      {...props}
    />
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-8 text-sm text-ink-2">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />
      {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-lg border border-line bg-surface-2 p-4 text-sm">
      <div className="font-medium text-loss">Something went wrong</div>
      <div className="mt-1 text-ink-2">{message}</div>
      {onRetry && (
        <Button variant="secondary" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line p-6 text-center text-sm">
      <div className="font-medium text-ink">{title}</div>
      {children && <div className="mt-1 text-ink-2">{children}</div>}
    </div>
  );
}

export function SimulationTag() {
  return (
    <span className="inline-flex items-center rounded bg-warn px-1.5 py-0.5 text-[11px] font-bold tracking-wide text-on-warn">
      PAPER TRADING · SIMULATION
    </span>
  );
}
