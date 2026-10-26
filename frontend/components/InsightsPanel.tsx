"use client";

import type { Insights } from "@/lib/api";
import { Card, ErrorState, Loading } from "./ui";

export function InsightsPanel({ data, error, loading, reload }: {
  data: Insights | null;
  error: { message: string } | null;
  loading: boolean;
  reload: () => void;
}) {
  return (
    <Card
      title="AI insights"
      actions={
        data && (
          <span className="text-xs text-muted">
            {data.generated_by === "rules+llm" ? `Summary by ${data.model}` : "Rule-based explanations"}
          </span>
        )
      }
    >
      {!data && loading && <Loading label="Analysing portfolio…" />}
      {error && !data && <ErrorState message={error.message} onRetry={reload} />}
      {data && (
        <div className={`space-y-3 transition-opacity ${loading ? "opacity-60" : ""}`}>
          {data.summary && <p className="rounded-lg bg-surface-2 p-3 text-sm text-ink">{data.summary}</p>}
          {data.llm_error && <p className="text-xs text-muted">AI summary unavailable: {data.llm_error}</p>}
          <ul className="space-y-3">
            {data.insights.map((i, idx) => (
              <li key={idx} className="text-sm">
                <div className="flex items-center gap-1.5 font-medium text-ink">
                  {i.severity === "attention" && (
                    <span className="rounded bg-warn px-1 text-[10px] font-bold text-on-warn">NOTE</span>
                  )}
                  {i.title}
                </div>
                <p className="mt-0.5 text-ink-2">{i.text}</p>
              </li>
            ))}
          </ul>
          <p className="border-t border-line pt-3 text-xs text-muted">{data.disclaimer}</p>
        </div>
      )}
    </Card>
  );
}
