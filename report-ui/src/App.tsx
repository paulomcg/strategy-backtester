import { useEffect, useState } from "react"
import { RunHeader } from "@/components/RunHeader"
import { MetricsSummary } from "@/components/MetricsSummary"
import { EquityChart } from "@/components/EquityChart"
import { TradesPanel } from "@/components/TradesPanel"
import { TradeStatsPanel } from "@/components/TradeStatsPanel"
import { PerAssetPanel } from "@/components/PerAssetPanel"
import { RunDetailsPanel } from "@/components/RunDetailsPanel"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { TriangleAlert } from "lucide-react"
import type { ReportPayload } from "@/types"
import { fixtureReport } from "@/lib/fixture"

function loadReport(): ReportPayload {
  if (typeof window !== "undefined" && window.__RUN_DATA__) {
    return window.__RUN_DATA__
  }
  return fixtureReport
}

export default function App() {
  const [report] = useState<ReportPayload>(() => loadReport())

  useEffect(() => {
    document.documentElement.classList.add("dark")
  }, [])

  const { meta, metrics, equity, fills } = report

  return (
    <div className="min-h-screen bg-background text-foreground">
      <RunHeader meta={meta} />

      <main className="mx-auto max-w-[1400px] px-6 py-6 space-y-6">
        {/* Title block */}
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              {meta.title ?? `Backtest ${meta.asset}`}
            </h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Deterministic OHLCV replay through portfolio-manager · realized
              PnL, risk, and execution audit.
            </p>
          </div>
          <Badge
            variant="outline"
            className="font-mono text-[10px] uppercase tracking-wider"
          >
            portfolio-manager runtime
          </Badge>
        </div>

        {metrics.warning && (
          <Alert
            variant="default"
            className="border-amber-500/40 bg-amber-500/10"
          >
            <TriangleAlert className="size-4 text-amber-500" />
            <AlertTitle className="font-medium">
              Insufficient signal
            </AlertTitle>
            <AlertDescription>{metrics.warning}</AlertDescription>
          </Alert>
        )}

        <MetricsSummary metrics={metrics} meta={meta} />

        <Card className="border-border bg-card py-0 shadow-none gap-0">
          <CardHeader className="px-5 py-4 border-b flex flex-row items-center justify-between gap-2">
            <CardTitle className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground font-medium">
              Equity curve
            </CardTitle>
            <div className="flex items-center gap-4 text-[11px] text-muted-foreground tabular-nums">
              <LegendSwatch color="var(--positive)" label="equity" />
              <LegendSwatch color="var(--border)" label="initial" dashed />
              {metrics.max_drawdown_trough_ts && (
                <LegendSwatch
                  color="var(--destructive)"
                  label="max DD trough"
                  dashed
                />
              )}
            </div>
          </CardHeader>
          <CardContent className="px-3 pt-4 pb-3">
            <EquityChart
              data={equity}
              initialEquity={metrics.initial_equity_usd}
              maxDrawdownPeakTs={metrics.max_drawdown_peak_ts}
              maxDrawdownTroughTs={metrics.max_drawdown_trough_ts}
            />
          </CardContent>
        </Card>

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2 space-y-6">
            <TradeStatsPanel stats={metrics.trades} />
            <TradesPanel fills={fills} />
          </div>
          <div className="space-y-6">
            <PerAssetPanel metrics={metrics} />
            <RunDetailsPanel meta={meta} metrics={metrics} />
          </div>
        </div>

        <footer className="pt-6 pb-12 text-center text-[11px] text-muted-foreground">
          strategy-backtester · self-contained report · open offline · audit:{" "}
          <span className="font-mono">pm-state/audit.jsonl</span>
        </footer>
      </main>
    </div>
  )
}

function LegendSwatch({
  color,
  label,
  dashed = false,
}: {
  color: string
  label: string
  dashed?: boolean
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="inline-block h-[2px] w-5"
        style={{
          background: dashed
            ? `repeating-linear-gradient(90deg, ${color} 0 4px, transparent 4px 8px)`
            : color,
        }}
      />
      {label}
    </span>
  )
}
