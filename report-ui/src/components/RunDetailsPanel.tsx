import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import type { Metrics, RunMeta } from "@/types"
import { fmtUsd } from "@/lib/format"

interface RunDetailsPanelProps {
  meta: RunMeta
  metrics: Metrics
}

export function RunDetailsPanel({ meta, metrics }: RunDetailsPanelProps) {
  const rows: { label: string; value: React.ReactNode }[] = [
    { label: "Strategy", value: <Mono>{meta.strategy_path}</Mono> },
    { label: "Rules", value: <Mono>{meta.rules_path}</Mono> },
    { label: "OHLCV", value: <Mono>{meta.ohlcv_path}</Mono> },
    { label: "Asset", value: meta.asset },
    { label: "Chain", value: meta.chain },
    { label: "Initial capital", value: fmtUsd(meta.initial_usd) },
    { label: "Bars processed", value: meta.bars_processed },
    {
      label: "Periods / year",
      value: metrics.periods_per_year ?? "—",
    },
    {
      label: "PM call failures",
      value: (
        <span
          className={
            meta.pm_call_failures > 0 ? "text-destructive" : ""
          }
        >
          {meta.pm_call_failures}
        </span>
      ),
    },
    {
      label: "Calmar",
      value: <span className="tabular-nums">{metrics.calmar.toFixed(2)}</span>,
    },
  ]

  return (
    <Card className="border-border bg-card py-0 shadow-none gap-0">
      <CardHeader className="px-5 py-4 border-b flex flex-row items-center justify-between gap-2">
        <CardTitle className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground font-medium">
          Run details
        </CardTitle>
        <Badge
          variant="outline"
          className="font-mono text-[10px] uppercase tracking-wider"
        >
          schema v{metrics.schema_version}
        </Badge>
      </CardHeader>
      <CardContent className="p-0">
        <dl className="divide-y divide-border/60 text-sm">
          {rows.map((r) => (
            <div
              key={r.label}
              className="flex items-start justify-between gap-4 px-5 py-2.5"
            >
              <dt className="text-xs text-muted-foreground pt-0.5">
                {r.label}
              </dt>
              <dd className="text-right tabular-nums max-w-[60%] truncate">
                {r.value}
              </dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}

function Mono({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-[11px] text-foreground/90 break-all">
      {children}
    </span>
  )
}
