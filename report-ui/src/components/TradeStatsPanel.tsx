import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import type { TradeStats } from "@/types"
import { fmtPct, fmtUsdSigned } from "@/lib/format"

interface TradeStatsPanelProps {
  stats: TradeStats
}

export function TradeStatsPanel({ stats }: TradeStatsPanelProps) {
  const winPct = (stats.win_rate || 0) * 100

  return (
    <Card className="border-border bg-card py-0 shadow-none gap-0">
      <CardHeader className="px-5 py-4 border-b">
        <CardTitle className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground font-medium">
          Trade activity
        </CardTitle>
      </CardHeader>
      <CardContent className="p-5 space-y-4">
        <div>
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-muted-foreground">Win rate</span>
            <span className="text-sm font-semibold tabular-nums">
              {fmtPct(winPct, 1)}
            </span>
          </div>
          <Progress value={winPct} className="h-1.5 mt-2" />
          <div className="flex justify-between text-[11px] text-muted-foreground mt-1.5 tabular-nums">
            <span>{stats.winners} winners</span>
            <span>{stats.losers} losers</span>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3 pt-2">
          <Stat
            label="Closed trades"
            value={stats.trades}
            mono
          />
          <Stat
            label="Expectancy / trade"
            value={fmtUsdSigned(stats.expectancy_usd)}
            tone={stats.expectancy_usd >= 0 ? "positive" : "negative"}
          />
          <Stat
            label="Total realized PnL"
            value={fmtUsdSigned(stats.total_pnl_usd)}
            tone={stats.total_pnl_usd >= 0 ? "positive" : "negative"}
          />
        </div>

        <div className="text-[11px] text-muted-foreground pt-3 border-t border-border/60">
          Realized PnL only — open positions are not counted. Expectancy is
          mean PnL per closed trade.
        </div>
      </CardContent>
    </Card>
  )
}

function Stat({
  label,
  value,
  tone = "default",
  mono = false,
}: {
  label: string
  value: React.ReactNode
  tone?: "default" | "positive" | "negative"
  mono?: boolean
}) {
  const toneClass =
    tone === "positive"
      ? "text-positive"
      : tone === "negative"
        ? "text-destructive"
        : "text-foreground"
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div
        className={`mt-1 font-semibold tabular-nums ${toneClass} ${
          mono ? "text-2xl" : "text-base"
        }`}
      >
        {value}
      </div>
    </div>
  )
}
