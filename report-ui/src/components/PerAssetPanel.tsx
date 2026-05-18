import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { Metrics } from "@/types"
import { fmtUsdSigned } from "@/lib/format"
import { cn } from "@/lib/utils"

interface PerAssetPanelProps {
  metrics: Metrics
}

export function PerAssetPanel({ metrics }: PerAssetPanelProps) {
  const entries = Object.entries(metrics.per_asset_pnl_usd).sort(
    (a, b) => b[1] - a[1],
  )
  const max = Math.max(...entries.map(([, v]) => Math.abs(v)), 1)

  return (
    <Card className="border-border bg-card py-0 shadow-none gap-0">
      <CardHeader className="px-5 py-4 border-b">
        <CardTitle className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground font-medium">
          Realized PnL by asset
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {entries.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            no realized PnL recorded
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
                  Asset
                </TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium text-right">
                  PnL
                </TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium w-1/2">
                  &nbsp;
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map(([asset, pnl]) => {
                const positive = pnl >= 0
                const widthPct = (Math.abs(pnl) / max) * 100
                return (
                  <TableRow key={asset} className="border-border/60">
                    <TableCell className="font-medium text-sm">{asset}</TableCell>
                    <TableCell
                      className={cn(
                        "text-right tabular-nums text-sm font-semibold",
                        positive ? "text-positive" : "text-destructive",
                      )}
                    >
                      {fmtUsdSigned(pnl)}
                    </TableCell>
                    <TableCell className="py-2 align-middle">
                      <div className="h-1.5 w-full rounded-full bg-border/50 overflow-hidden">
                        <div
                          className={cn(
                            "h-full",
                            positive ? "bg-positive/70" : "bg-destructive/70",
                          )}
                          style={{ width: `${widthPct}%` }}
                        />
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
