import { MetricCard } from "@/components/MetricCard"
import type { Metrics, RunMeta } from "@/types"
import { fmtPct, fmtUsd, fmtNum } from "@/lib/format"

interface MetricsSummaryProps {
  metrics: Metrics
  meta: RunMeta
}

export function MetricsSummary({ metrics, meta }: MetricsSummaryProps) {
  const returnTone = metrics.total_return_pct >= 0 ? "positive" : "negative"
  const ddTone = "negative"

  return (
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <MetricCard
        label="Total return"
        value={fmtPct(metrics.total_return_pct, 2, true)}
        tone={returnTone}
        size="lg"
        hint={`${fmtUsd(metrics.initial_equity_usd, true)} → ${fmtUsd(
          metrics.final_equity_usd,
          true,
        )}`}
      />
      <MetricCard
        label="CAGR"
        value={fmtPct(metrics.cagr_pct, 2, true)}
        tone={metrics.cagr_pct >= 0 ? "positive" : "negative"}
        size="lg"
      />
      <MetricCard
        label="Sharpe"
        value={fmtNum(metrics.sharpe, 2)}
        tone={metrics.sharpe >= 1 ? "positive" : metrics.sharpe < 0 ? "negative" : "default"}
        size="lg"
      />
      <MetricCard
        label="Sortino"
        value={fmtNum(metrics.sortino, 2)}
        tone={metrics.sortino >= 1 ? "positive" : metrics.sortino < 0 ? "negative" : "default"}
        size="lg"
      />
      <MetricCard
        label="Max drawdown"
        value={fmtPct(metrics.max_drawdown_pct, 2)}
        tone={ddTone}
        size="lg"
        hint="from high-water mark"
      />
      <MetricCard
        label="Bars · trades"
        value={
          <span>
            {meta.bars_processed}
            <span className="mx-1 text-muted-foreground">·</span>
            {metrics.trades.trades}
          </span>
        }
        size="lg"
        hint={`${meta.fills_total} fills`}
      />
    </section>
  )
}
